"""Deterministic search solver for reviewed single-player levels.

Uses an internal tuple-based state engine for performance:
- States are 6-tuples: (day, node, cash, water, food, finished)
- Actions are stored as 9-tuples: (kind, from_node, to_node, weather, cw, cf, income, bw, bf)
- Parents map: tuple_state -> (tuple_state|None, action_tuple|None)
- Public API and output formats are unchanged.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import (
    Action,
    LevelConfig,
    PlayerState,
    RESOURCE_FOOD,
    RESOURCE_WATER,
    SolutionTrace,
    TraceStep,
    WEATHER_STORM,
)
from .rules import (
    carried_weight,
    daily_consumption,
    is_weight_feasible,
    prune_dominated_states,
    purchase_options,
    resource_cost,
    terminal_refund,
    terminal_value,
)
from .validate import validate_level

# ---------------------------------------------------------------------------
# State tuple format (used throughout the tuple engine):
#   (day, node, cash, water, food, finished)
# Action tuple format:
#   (kind, from_node, to_node, weather, consume_water, consume_food, income, buy_water, buy_food)
# Parent value format:
#   (parent_state_tuple | None, action_tuple | None)
# ---------------------------------------------------------------------------

TupleState = Tuple[int, int, int, int, int, bool]
TupleAction = Tuple  # 9 elements
ParentEntry = Tuple[Optional[TupleState], Optional[TupleAction]]
TupleParentMap = Dict[TupleState, ParentEntry]


ParentMap = Dict[PlayerState, Tuple[Optional[PlayerState], Optional[Action]]]


class SolverBlockedError(RuntimeError):
    """Raised when a level lacks reviewed data needed for final solving."""


def _bucket_key(state: PlayerState) -> Tuple[int, int, bool]:
    return state.day, state.node, state.finished


def _prune_bucket(states: Iterable[PlayerState], max_states: int) -> List[PlayerState]:
    survivors = prune_dominated_states(states)
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


def _reconstruct_from_tuples(
    level: LevelConfig,
    final_state: TupleState,
    parents: TupleParentMap,
    trace_obj: Dict[str, Any],
) -> SolutionTrace:
    """Build SolutionTrace from tuple parent chain.  trace_obj holds mutable metadata."""
    chain: List[Tuple[TupleState, Optional[TupleAction]]] = []
    cursor: Optional[TupleState] = final_state
    while cursor is not None:
        previous, action = parents[cursor]
        chain.append((cursor, action))
        cursor = previous
    chain.reverse()
    steps: List[TraceStep] = []
    for st, act in chain:
        ps = PlayerState(st[0], st[1], st[2], st[3], st[4], st[5])
        if act is None:
            steps.append(TraceStep(day=st[0], state=ps, action=None))
        else:
            if act[0] == "buy_start":
                note = "initial purchase"
            elif act[7] != 0 or act[8] != 0:
                note = "village purchase"
            else:
                note = ""
            a = Action(
                kind=act[0], from_node=act[1], to_node=act[2], weather=act[3],
                consume_water=act[4], consume_food=act[5], income=act[6],
                buy_water=act[7], buy_food=act[8],
                note=note,
            )
            steps.append(TraceStep(day=st[0], state=ps, action=a))
    return SolutionTrace(
        level_id=level.level_id,
        objective_value=terminal_value(level, PlayerState(*final_state)),
        feasible=True, steps=steps, status="optimal_search",
        message="best reviewed deterministic trace found",
        metadata=trace_obj,
    )


# -- Tuple engine helpers (solver-local, avoids PlayerState allocations) ----------

def _tuple_resource_cost(
    level: LevelConfig, add_w: int, add_f: int, price_mult: float
) -> int:
    if add_w < 0 or add_f < 0:
        return 10**9
    w_spec = level.resources[RESOURCE_WATER]
    f_spec = level.resources[RESOURCE_FOOD]
    return int(round(
        add_w * w_spec.base_price * price_mult + add_f * f_spec.base_price * price_mult
    ))


def _tuple_purchase_options(
    level: LevelConfig,
    state: TupleState,
    price_mult: float,
    max_options: int,
    step: int,
) -> List[TupleState]:
    """Fast tuple-based purchase generator, equivalent to rules.purchase_options."""
    w_spec = level.resources[RESOURCE_WATER]
    f_spec = level.resources[RESOURCE_FOOD]
    max_water = level.carry_limit_kg // w_spec.mass_kg
    max_food = level.carry_limit_kg // f_spec.mass_kg
    day, node, cash, water, food, finished = state
    step = max(1, step)
    w_vals = set(range(water, max_water + 1, step))
    w_vals.add(water); w_vals.add(max_water)
    candidates: List[TupleState] = []
    for w in sorted(w_vals):
        max_f = min(max_food, (level.carry_limit_kg - w * w_spec.mass_kg) // f_spec.mass_kg)
        if max_f < food:
            continue
        f_vals = set(range(food, max_f + 1, step))
        f_vals.add(max_f)
        for f in sorted(f_vals):
            cost = _tuple_resource_cost(level, w - water, f - food, price_mult)
            if cost <= cash:
                candidates.append((day, node, cash - cost, w, f, finished))
    # Dedup
    seen: set[TupleState] = set()
    uniq: List[TupleState] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    # Tuple Fenwick prune
    pruned = _tuple_prune_dominated(uniq)
    if len(pruned) <= max_options:
        return pruned
    pruned.sort(key=lambda s: (s[2] + 3*s[3] + 4*s[4], s[2], s[3]+s[4]), reverse=True)
    return pruned[:max_options]


def _tuple_prune_dominated(states: List[TupleState]) -> List[TupleState]:
    """Fenwick-based Pareto dominance pruning on tuple states (same-day bucket)."""
    if not states:
        return []
    max_water = max(s[3] for s in states)
    tree = [-1] * (max_water + 3)

    def _query(idx: int) -> int:
        best = -1
        while idx > 0:
            if tree[idx] > best:
                best = tree[idx]
            idx -= idx & -idx
        return best

    def _update(idx: int, val: int) -> None:
        while idx < len(tree):
            if val > tree[idx]:
                tree[idx] = val
            idx += idx & -idx

    survivors: List[TupleState] = []
    for s in sorted(states, key=lambda x: (x[2], x[3], x[4]), reverse=True):
        rw = max_water - s[3] + 1
        if _query(rw) >= s[4]:
            continue
        survivors.append(s)
        _update(rw, s[4])
    return survivors


def _tuple_prune_bucket(states: List[TupleState], max_states: int) -> List[TupleState]:
    survivors = _tuple_prune_dominated(states)
    if len(survivors) <= max_states:
        return survivors
    survivors.sort(key=lambda s: (s[2] + 0.5*s[3] + 1.0*s[4], s[2], s[3]+s[4]), reverse=True)
    return survivors[:max_states]


def _tuple_prune_all(
    states: List[TupleState], max_states_per_bucket: int
) -> List[TupleState]:
    buckets: Dict[Tuple[int, int, bool], List[TupleState]] = defaultdict(list)
    for s in states:
        buckets[(s[0], s[1], s[5])].append(s)
    pruned: List[TupleState] = []
    for bucket in buckets.values():
        pruned.extend(_tuple_prune_bucket(bucket, max_states_per_bucket))
    return pruned


def _precompute_consumption_table(
    level: LevelConfig,
    weather: Tuple[str, ...],
) -> List[Dict[str, Tuple[int, int]]]:
    """action_table[day] = {kind: (water_consumption, food_consumption)}"""
    table: List[Dict[str, Tuple[int, int]]] = []
    for d in range(level.deadline):
        w = weather[d]
        table.append({
            "stay": (level.resources[RESOURCE_WATER].consumption(w, level.rules.stay_multiplier),
                     level.resources[RESOURCE_FOOD].consumption(w, level.rules.stay_multiplier)),
            "move": (level.resources[RESOURCE_WATER].consumption(w, level.rules.move_multiplier),
                     level.resources[RESOURCE_FOOD].consumption(w, level.rules.move_multiplier)),
            "mine": (level.resources[RESOURCE_WATER].consumption(w, level.rules.mine_multiplier),
                     level.resources[RESOURCE_FOOD].consumption(w, level.rules.mine_multiplier)),
        })
    return table


def _solve_tuple_engine(
    level: LevelConfig,
    weather: Tuple[str, ...],
    max_states_per_bucket: int,
    max_purchase_options: int,
    purchase_step: int,
) -> SolutionTrace:
    """Core label-setting search on tuple states."""
    action_table = _precompute_consumption_table(level, weather)

    # Pre-compute terminal refund constants (avoids PlayerState allocation)
    water_refund = level.resources[RESOURCE_WATER].base_price * level.rules.refund_multiplier
    food_refund = level.resources[RESOURCE_FOOD].base_price * level.rules.refund_multiplier

    def _tv(st: TupleState) -> float:
        return st[2] + st[3] * water_refund + st[4] * food_refund

    # -- initial purchase frontier ------------------------------------------
    start = (0, level.start_node, level.initial_cash, 0, 0, False)
    start_purchase_options = _tuple_purchase_options(
        level, start, level.rules.start_price_multiplier, max_purchase_options, purchase_step
    )
    # filter: water>0 and food>0 and weight feasible
    w_spec = level.resources[RESOURCE_WATER]
    f_spec = level.resources[RESOURCE_FOOD]
    init_states: List[TupleState] = []
    for s in start_purchase_options:
        if s[3] > 0 and s[4] > 0:
            wt = s[3] * w_spec.mass_kg + s[4] * f_spec.mass_kg
            if wt <= level.carry_limit_kg:
                init_states.append(s)

    parents: TupleParentMap = {}
    for s in init_states:
        buy_action: TupleAction = (
            "buy_start",
            level.start_node,
            level.start_node,
            None,
            0,
            0,
            0,
            s[3],
            s[4],
        )
        parents[s] = (None, buy_action)

    frontier = _tuple_prune_all(init_states, max_states_per_bucket)
    best_final: Optional[TupleState] = None
    best_tv = -1e18
    visited_count = len(frontier)
    goal_node = level.goal_node
    base_income = level.base_income
    villages_set = set(level.villages)
    mines_set = set(level.mines)

    for day in range(level.deadline):
        cons = action_table[day]
        cw_stay, cf_stay = cons["stay"]
        cw_move, cf_move = cons["move"]
        cw_mine, cf_mine = cons["mine"]
        next_states: List[TupleState] = []
        for state in frontier:
            if state[5]:  # finished
                tv = _tv(state)
                if tv > best_tv:
                    best_tv = tv; best_final = state
                continue
            d, node, cash, water, food, finished = state

            # -- stay ----------------------------------------------------------
            nw = water - cw_stay; nf = food - cf_stay
            if nw > 0 and nf > 0:
                ns = (d+1, node, cash, nw, nf, False)
                act: TupleAction = ("stay", node, node, weather[day], cw_stay, cf_stay, 0, 0, 0)
                if ns not in parents:
                    parents[ns] = (state, act)
                next_states.append(ns)

            # -- mine ----------------------------------------------------------
            if node in mines_set:
                nw = water - cw_mine; nf = food - cf_mine
                if nw > 0 and nf > 0:
                    ns = (d+1, node, cash + base_income, nw, nf, False)
                    act = ("mine", node, node, weather[day], cw_mine, cf_mine, base_income, 0, 0)
                    if ns not in parents:
                        parents[ns] = (state, act)
                    next_states.append(ns)

            # -- move (no storm) -----------------------------------------------
            if weather[day] != WEATHER_STORM:
                for nbr in level.neighbors(node):
                    nw = water - cw_move; nf = food - cf_move
                    if nw < 0 or nf < 0:
                        continue
                    finished_n = nbr == goal_node
                    if not finished_n and (nw <= 0 or nf <= 0):
                        continue
                    ns = (d+1, nbr, cash, nw, nf, finished_n)
                    act = ("move", node, nbr, weather[day], cw_move, cf_move, 0, 0, 0)
                    if finished_n:
                        tv = _tv(ns)
                        if tv > best_tv:
                            best_tv = tv; best_final = ns
                        if ns not in parents:
                            parents[ns] = (state, act)
                    else:
                        if ns not in parents:
                            parents[ns] = (state, act)
                        next_states.append(ns)

        # -- village purchase post-processing ----------------------------------
        pruned_next: List[TupleState] = []
        for ns in next_states:
            if ns[5]:  # finished
                pruned_next.append(ns)
                continue
            if ns[1] not in villages_set:
                pruned_next.append(ns)
                continue
            purchased = _tuple_purchase_options(
                level, ns, level.rules.village_price_multiplier, max_purchase_options, purchase_step
            )
            parent_entry = parents[ns]
            parent_s = parent_entry[0]  # real predecessor
            base_act = parent_entry[1]   # action that produced ns
            for ps in purchased:
                # base_act is: (kind, from_node, to_node, weather, cw, cf, income, bw, bf)
                if ps == ns:
                    new_act: TupleAction = (
                        base_act[0], base_act[1], base_act[2], base_act[3],
                        base_act[4], base_act[5], base_act[6], 0, 0,
                    )
                else:
                    new_act = (
                        base_act[0], base_act[1], base_act[2], base_act[3],
                        base_act[4], base_act[5], base_act[6],
                        ps[3] - ns[3], ps[4] - ns[4],
                    )
                if ps not in parents:
                    parents[ps] = (parent_s, new_act)
                pruned_next.append(ps)

        # Deduplicate before pruning (avoids reprocessing same state)
        seen_nf: set[TupleState] = set()
        uniq_nf: List[TupleState] = []
        for s in pruned_next:
            if s not in seen_nf:
                seen_nf.add(s)
                uniq_nf.append(s)
        frontier = _tuple_prune_all(uniq_nf, max_states_per_bucket)
        visited_count += len(frontier)
        if not frontier and best_final is not None:
            break

    if best_final is None:
        return SolutionTrace(
            level_id=level.level_id, objective_value=float("-inf"), feasible=False,
            status="infeasible",
            message="no feasible route reached the goal before deadline",
            metadata={"visited_states": visited_count, "solver_engine": "tuple_exact_v2"},
        )

    final_tv = terminal_value(level, PlayerState(*best_final))
    meta = {
        "solver_engine": "tuple_exact_v2",
        "final_terminal_value": final_tv,
        "visited_states": visited_count,
        "max_states_per_bucket": max_states_per_bucket,
        "purchase_step": purchase_step,
    }
    return _reconstruct_from_tuples(level, best_final, parents, meta)


# Original (kept for backward compat and tests) --------------------------------

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

    # Delegate to tuple engine for speed (public API unchanged)
    return _solve_tuple_engine(
        level, weather,
        max_states_per_bucket=max_states_per_bucket,
        max_purchase_options=max_purchase_options,
        purchase_step=purchase_step,
    )


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
