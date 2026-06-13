"""Fast baseline strategy generation for visualization and sanity checks."""

from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Action, LevelConfig, PlayerState, SolutionTrace, TraceStep, WEATHER_STORM
from .rules import carried_weight, daily_consumption, resource_cost, terminal_value


def shortest_path(level: LevelConfig, start: Optional[int] = None, goal: Optional[int] = None) -> Optional[List[int]]:
    source = level.start_node if start is None else start
    target = level.goal_node if goal is None else goal
    queue = deque([(source, [source])])
    seen = {source}
    while queue:
        node, path = queue.popleft()
        if node == target:
            return path
        for neighbor in level.neighbors(node):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return None


def timed_actions_for_path(
    level: LevelConfig,
    path: List[int],
    weather_sequence: Optional[Tuple[str, ...]] = None,
) -> List[Tuple[str, int, int, str]]:
    weather_values = weather_sequence or level.weather
    if not weather_values:
        raise ValueError("baseline requires known weather")
    current = path[0]
    path_index = 0
    actions: List[Tuple[str, int, int, str]] = []
    for day, weather in enumerate(weather_values, 1):
        if path_index >= len(path) - 1:
            break
        if weather == WEATHER_STORM:
            actions.append(("stay", current, current, weather))
            continue
        next_node = path[path_index + 1]
        actions.append(("move", current, next_node, weather))
        current = next_node
        path_index += 1
    if path_index < len(path) - 1:
        raise ValueError("path cannot reach goal before deadline under storm days")
    return actions


def baseline_shortest_path_trace(
    level: LevelConfig,
    weather_sequence: Optional[Tuple[str, ...]] = None,
) -> SolutionTrace:
    path = shortest_path(level)
    if not path:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="baseline_infeasible",
            message="no graph path from start to goal",
        )
    try:
        timed_actions = timed_actions_for_path(level, path, weather_sequence=weather_sequence)
    except ValueError as exc:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="baseline_infeasible",
            message=str(exc),
            metadata={"path": path},
        )

    total_water = 0
    total_food = 0
    consumptions: List[Tuple[int, int]] = []
    for kind, _frm, _to, weather in timed_actions:
        multiplier = level.rules.move_multiplier if kind == "move" else level.rules.stay_multiplier
        water, food = daily_consumption(level, weather, multiplier)
        consumptions.append((water, food))
        total_water += water
        total_food += food

    if carried_weight(level, total_water, total_food) > level.carry_limit_kg:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="baseline_infeasible",
            message="shortest-path resource load exceeds carry limit",
            metadata={"path": path, "water": total_water, "food": total_food},
        )
    cost = resource_cost(level, total_water, total_food, level.rules.start_price_multiplier)
    if cost > level.initial_cash:
        return SolutionTrace(
            level_id=level.level_id,
            objective_value=float("-inf"),
            feasible=False,
            status="baseline_infeasible",
            message="shortest-path initial purchase exceeds cash",
            metadata={"path": path, "cost": cost},
        )

    state = PlayerState(0, level.start_node, level.initial_cash - cost, total_water, total_food, False)
    steps = [
        TraceStep(
            day=0,
            state=state,
            action=Action(
                kind="buy_start",
                from_node=level.start_node,
                to_node=level.start_node,
                buy_water=total_water,
                buy_food=total_food,
                note="baseline exact purchase",
            ),
        )
    ]
    for day, ((kind, frm, to, weather), (water_used, food_used)) in enumerate(zip(timed_actions, consumptions), 1):
        state = PlayerState(
            day=day,
            node=to,
            cash=state.cash,
            water=state.water - water_used,
            food=state.food - food_used,
            finished=to == level.goal_node,
        )
        steps.append(
            TraceStep(
                day=day,
                state=state,
                action=Action(
                    kind=kind,
                    from_node=frm,
                    to_node=to,
                    weather=weather,
                    consume_water=water_used,
                    consume_food=food_used,
                    note="baseline shortest path",
                ),
            )
        )

    final_state = steps[-1].state
    return SolutionTrace(
        level_id=level.level_id,
        objective_value=terminal_value(level, final_state),
        feasible=True,
        steps=steps,
        status="baseline_shortest_path",
        message="feasible baseline route generated from shortest path",
        metadata={"path": path, "total_water": total_water, "total_food": total_food, "cost": cost},
    )
