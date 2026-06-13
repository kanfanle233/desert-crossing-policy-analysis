"""Deterministic search solver for reviewed single-player levels."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import (
    Action,
    LevelConfig,
    PlayerState,
    SolutionTrace,
    TraceStep,
    WEATHER_STORM,
)
from .rules import (
    daily_consumption,
    is_weight_feasible,
    purchase_options,
    terminal_value,
)
from .validate import validate_level


ParentMap = Dict[PlayerState, Tuple[Optional[PlayerState], Optional[Action]]]


class SolverBlockedError(RuntimeError):
    """Raised when a level lacks reviewed data needed for final solving."""


def _bucket_key(state: PlayerState) -> Tuple[int, int, bool]:
    return state.day, state.node, state.finished


def _prune_bucket(states: Iterable[PlayerState], max_states: int) -> List[PlayerState]:
    states = list(set(states))
    survivors: List[PlayerState] = []
    for state in sorted(states, key=lambda s: (s.cash, s.water, s.food), reverse=True):
        dominated = False
        for other in survivors:
            if (
                other.cash >= state.cash
                and other.water >= state.water
                and other.food >= state.food
                and (other.cash, other.water, other.food) != (state.cash, state.water, state.food)
            ):
                dominated = True
                break
        if not dominated:
            survivors.append(state)
    if len(survivors) <= max_states:
        return survivors
    survivors.sort(
        key=lambda s: (
            s.cash + 0.5 * s.water + 1.0 * s.food,
            s.cash,
            s.water + s.food,
        ),
        reverse=True,
    )
    return survivors[:max_states]


def _prune_all(states: Iterable[PlayerState], max_states_per_bucket: int) -> List[PlayerState]:
    buckets: Dict[Tuple[int, int, bool], List[PlayerState]] = defaultdict(list)
    for state in states:
        buckets[_bucket_key(state)].append(state)
    pruned: List[PlayerState] = []
    for bucket_states in buckets.values():
        pruned.extend(_prune_bucket(bucket_states, max_states_per_bucket))
    return pruned


def _apply_daily_action(
    level: LevelConfig,
    state: PlayerState,
    weather: str,
    kind: str,
    to_node: int,
) -> Optional[Tuple[PlayerState, Action]]:
    if kind == "move":
        multiplier = level.rules.move_multiplier
        income = 0
    elif kind == "mine":
        multiplier = level.rules.mine_multiplier
        income = level.base_income
    elif kind == "stay":
        multiplier = level.rules.stay_multiplier
        income = 0
    else:
        raise ValueError("Unsupported action kind: %s" % kind)

    consume_water, consume_food = daily_consumption(level, weather, multiplier)
    next_water = state.water - consume_water
    next_food = state.food - consume_food
    next_cash = state.cash + income
    next_day = state.day + 1
    finished = to_node == level.goal_node

    if next_water < 0 or next_food < 0:
        return None
    if not finished and (next_water <= 0 or next_food <= 0):
        return None
    next_state = PlayerState(next_day, to_node, next_cash, next_water, next_food, finished)
    action = Action(
        kind=kind,
        from_node=state.node,
        to_node=to_node,
        weather=weather,
        consume_water=consume_water,
        consume_food=consume_food,
        income=income,
    )
    return next_state, action


def _post_action_purchase_states(
    level: LevelConfig,
    post_state: PlayerState,
    action: Action,
    max_purchase_options: int,
    purchase_step: int,
) -> Iterable[Tuple[PlayerState, Action]]:
    if post_state.finished:
        yield post_state, action
        return
    if post_state.node not in level.villages:
        yield post_state, action
        return
    for purchased in purchase_options(
        level,
        post_state,
        price_multiplier=level.rules.village_price_multiplier,
        max_options=max_purchase_options,
        step=purchase_step,
    ):
        buy_action = Action(
            kind=action.kind,
            from_node=action.from_node,
            to_node=action.to_node,
            weather=action.weather,
            buy_water=purchased.water - post_state.water,
            buy_food=purchased.food - post_state.food,
            consume_water=action.consume_water,
            consume_food=action.consume_food,
            income=action.income,
            note="village purchase" if purchased != post_state else "",
        )
        yield purchased, buy_action


def _reconstruct(level: LevelConfig, final_state: PlayerState, parents: ParentMap) -> SolutionTrace:
    chain: List[Tuple[PlayerState, Optional[Action]]] = []
    cursor: Optional[PlayerState] = final_state
    while cursor is not None:
        previous, action = parents[cursor]
        chain.append((cursor, action))
        cursor = previous
    chain.reverse()
    steps = [TraceStep(day=state.day, state=state, action=action) for state, action in chain]
    return SolutionTrace(
        level_id=level.level_id,
        objective_value=terminal_value(level, final_state),
        feasible=True,
        steps=steps,
        status="optimal_search",
        message="best reviewed deterministic trace found",
        metadata={"final_terminal_value": terminal_value(level, final_state)},
    )


def solve_deterministic_level(
    level: LevelConfig,
    weather_sequence: Optional[Sequence[str]] = None,
    ignore_review: bool = False,
    max_states_per_bucket: int = 800,
    max_purchase_options: int = 500,
    purchase_step: int = 25,
) -> SolutionTrace:
    """Solve a single-player level with known weather using label search."""

    issues = validate_level(level, require_graph=True)
    hard_issues = []
    for issue in issues:
        if issue.startswith("review_required") and ignore_review:
            continue
        hard_issues.append(issue)
    if hard_issues:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="blocked",
            message="; ".join(hard_issues),
        )

    weather = tuple(weather_sequence or level.weather or ())
    if len(weather) != level.deadline:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="blocked",
            message="known weather sequence is required and must match deadline",
        )

    base_state = PlayerState(0, level.start_node, level.initial_cash, 0, 0, False)
    parents: ParentMap = {}
    frontier: List[PlayerState] = []
    for stocked in purchase_options(
        level,
        base_state,
        price_multiplier=level.rules.start_price_multiplier,
        max_options=max_purchase_options,
        step=purchase_step,
    ):
        buy_action = Action(
            kind="buy_start",
            from_node=level.start_node,
            to_node=level.start_node,
            buy_water=stocked.water,
            buy_food=stocked.food,
            note="initial purchase",
        )
        if stocked.water > 0 and stocked.food > 0 and is_weight_feasible(level, stocked.water, stocked.food):
            parents[stocked] = (None, buy_action)
            frontier.append(stocked)
    frontier = _prune_all(frontier, max_states_per_bucket)

    best_final: Optional[PlayerState] = None
    visited_count = len(frontier)
    for day in range(level.deadline):
        next_states: List[PlayerState] = []
        day_weather = weather[day]
        for state in frontier:
            if state.finished:
                if best_final is None or terminal_value(level, state) > terminal_value(level, best_final):
                    best_final = state
                continue
            actions: List[Tuple[str, int]] = [("stay", state.node)]
            if state.node in level.mines:
                actions.append(("mine", state.node))
            if day_weather != WEATHER_STORM:
                actions.extend(("move", nbr) for nbr in level.neighbors(state.node))
            for kind, to_node in actions:
                applied = _apply_daily_action(level, state, day_weather, kind, to_node)
                if applied is None:
                    continue
                post_state, action = applied
                for purchased, final_action in _post_action_purchase_states(
                    level,
                    post_state,
                    action,
                    max_purchase_options=max_purchase_options,
                    purchase_step=purchase_step,
                ):
                    if purchased not in parents:
                        parents[purchased] = (state, final_action)
                    next_states.append(purchased)
                    if purchased.finished:
                        if best_final is None or terminal_value(level, purchased) > terminal_value(level, best_final):
                            best_final = purchased
        frontier = _prune_all(next_states, max_states_per_bucket)
        visited_count += len(frontier)
        if not frontier and best_final is not None:
            break

    if best_final is None:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="infeasible",
            message="no feasible route reached the goal before deadline",
            metadata={"visited_states": visited_count},
        )
    trace = _reconstruct(level, best_final, parents)
    trace.metadata["visited_states"] = visited_count
    trace.metadata["max_states_per_bucket"] = max_states_per_bucket
    trace.metadata["purchase_step"] = purchase_step
    return trace


def write_trace_json(trace: SolutionTrace, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    objective_value = trace.objective_value
    safe_objective = objective_value if math.isfinite(objective_value) else None
    payload = {
        "level_id": trace.level_id,
        "objective_value": safe_objective,
        "feasible": trace.feasible,
        "status": trace.status,
        "message": trace.message,
        "metadata": trace.metadata,
        "rows": trace.to_rows(),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def write_trace_csv(trace: SolutionTrace, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = trace.to_rows()
    fieldnames = [
        "day",
        "node",
        "cash",
        "water",
        "food",
        "finished",
        "action",
        "from_node",
        "to_node",
        "weather",
        "buy_water",
        "buy_food",
        "consume_water",
        "consume_food",
        "income",
        "note",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
