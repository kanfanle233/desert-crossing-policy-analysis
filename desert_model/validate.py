"""Validation for level configs and solution traces."""

from __future__ import annotations

from typing import Iterable, List, Optional

from .models import LevelConfig, SolutionTrace, WEATHER_STORM
from .rules import carried_weight, terminal_value


def validate_level(level: LevelConfig, require_graph: bool = False) -> List[str]:
    issues: List[str] = []
    if level.deadline <= 0:
        issues.append("deadline must be positive")
    if level.start_node == level.goal_node:
        issues.append("start_node and goal_node should differ")
    if level.has_known_weather and len(level.weather or ()) != level.deadline:
        issues.append("known weather length must equal deadline")
    if not level.has_known_weather and not level.weather_policy:
        issues.append("unknown-weather level should define weather_policy")
    if require_graph and not level.adjacency:
        issues.append("adjacency is missing")
    if level.review_required:
        issues.append("review_required is true: map/formula data must be checked before final submission")
    if level.adjacency:
        for node, nbrs in level.adjacency.items():
            for nbr in nbrs:
                if node not in level.adjacency.get(nbr, ()):
                    issues.append("adjacency is not symmetric: %s -> %s" % (node, nbr))
    if level.players is None and level.level_id in (5, 6):
        issues.append("players is missing for multiplayer level")
    return issues


def validate_trace(level: LevelConfig, trace: SolutionTrace) -> List[str]:
    issues: List[str] = []
    if not trace.feasible:
        issues.append("trace is infeasible: %s" % trace.message)
        return issues
    if not trace.steps:
        issues.append("trace has no steps")
        return issues
    initial = trace.steps[0].state
    if initial.day != 0:
        issues.append("first trace step must be day 0")
    if initial.node != level.start_node:
        issues.append("first trace node must be start_node")
    seen_days = set()
    prev = None
    for step in trace.steps:
        state = step.state
        seen_days.add(state.day)
        if state.cash < 0:
            issues.append("negative cash at day %s" % state.day)
        if state.water < 0 or state.food < 0:
            issues.append("negative resource at day %s" % state.day)
        if carried_weight(level, state.water, state.food) > level.carry_limit_kg:
            issues.append("carry limit exceeded at day %s" % state.day)
        if prev is not None:
            if state.day != prev.state.day + 1:
                issues.append("nonconsecutive day at %s" % state.day)
            action = step.action
            if action and action.kind == "move":
                if level.weather and level.weather[state.day - 1] == WEATHER_STORM:
                    issues.append("move action on storm day %s" % state.day)
                if action.to_node not in level.neighbors(action.from_node):
                    issues.append("illegal move %s -> %s on day %s" % (action.from_node, action.to_node, state.day))
        prev = step
    final = trace.final_state()
    if final is None or final.node != level.goal_node or not final.finished:
        issues.append("trace does not end at goal")
    elif abs(trace.objective_value - terminal_value(level, final)) > 1e-6:
        issues.append("objective_value does not match final cash plus refund")
    if max(seen_days) > level.deadline:
        issues.append("trace exceeds deadline")
    return issues
