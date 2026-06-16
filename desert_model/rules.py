"""Resource accounting and multiplayer rule helpers."""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Tuple

from .models import LevelConfig, PlayerState, RESOURCE_FOOD, RESOURCE_WATER


def carried_weight(level: LevelConfig, water: int, food: int) -> int:
    return (
        water * level.resources[RESOURCE_WATER].mass_kg
        + food * level.resources[RESOURCE_FOOD].mass_kg
    )


def is_weight_feasible(level: LevelConfig, water: int, food: int) -> bool:
    return water >= 0 and food >= 0 and carried_weight(level, water, food) <= level.carry_limit_kg


def resource_cost(level: LevelConfig, water: int, food: int, price_multiplier: float) -> int:
    if water < 0 or food < 0:
        return 10**9  # Selling is not allowed; make it unaffordable
    return int(round(
        water * level.resources[RESOURCE_WATER].base_price * price_multiplier
        + food * level.resources[RESOURCE_FOOD].base_price * price_multiplier
    ))


def terminal_refund(level: LevelConfig, water: int, food: int) -> float:
    return (
        water * level.resources[RESOURCE_WATER].base_price * level.rules.refund_multiplier
        + food * level.resources[RESOURCE_FOOD].base_price * level.rules.refund_multiplier
    )


def terminal_value(level: LevelConfig, state: PlayerState) -> float:
    return state.cash + terminal_refund(level, state.water, state.food)


def daily_consumption(level: LevelConfig, weather: str, multiplier: float) -> Tuple[int, int]:
    water = level.resources[RESOURCE_WATER].consumption(weather, multiplier)
    food = level.resources[RESOURCE_FOOD].consumption(weather, multiplier)
    return water, food


def can_afford_purchase(level: LevelConfig, cash: int, add_water: int, add_food: int, multiplier: float) -> bool:
    return cash >= resource_cost(level, add_water, add_food, multiplier)


def purchase_options(
    level: LevelConfig,
    state: PlayerState,
    price_multiplier: float,
    max_options: int = 1500,
    step: int = 1,
) -> Iterable[PlayerState]:
    """Generate non-dominated resource purchase states reachable from a state."""

    water_spec = level.resources[RESOURCE_WATER]
    food_spec = level.resources[RESOURCE_FOOD]
    max_water = level.carry_limit_kg // water_spec.mass_kg
    max_food = level.carry_limit_kg // food_spec.mass_kg
    candidates = []
    step = max(1, int(step))
    water_values = set(range(state.water, max_water + 1, step))
    water_values.add(state.water)
    water_values.add(max_water)
    for water in sorted(water_values):
        max_food_for_weight = (level.carry_limit_kg - water * water_spec.mass_kg) // food_spec.mass_kg
        max_food_for_weight = min(max_food, max_food_for_weight)
        if max_food_for_weight < state.food:
            continue  # Can't keep current food with this water level
        food_values = set(range(state.food, max_food_for_weight + 1, step))
        food_values.add(max_food_for_weight)
        for food in sorted(food_values):
            add_water = water - state.water
            add_food = food - state.food
            cost = resource_cost(level, add_water, add_food, price_multiplier)
            if cost <= state.cash:
                candidates.append(PlayerState(state.day, state.node, state.cash - cost, water, food, state.finished))
    pruned = prune_dominated_states(candidates)
    if len(pruned) <= max_options:
        return pruned
    pruned.sort(key=lambda s: (s.cash + 3 * s.water + 4 * s.food, s.cash, s.water + s.food), reverse=True)
    return pruned[:max_options]


def dominates(left: PlayerState, right: PlayerState) -> bool:
    return (
        left.node == right.node
        and left.day == right.day
        and left.finished == right.finished
        and left.cash >= right.cash
        and left.water >= right.water
        and left.food >= right.food
        and (left.cash, left.water, left.food) != (right.cash, right.water, right.food)
    )


def prune_dominated_states(states: Iterable[PlayerState]) -> list[PlayerState]:
    unique: Dict[Tuple[int, int, int, int, int, bool], PlayerState] = {}
    for state in states:
        key = (state.day, state.node, state.cash, state.water, state.food, state.finished)
        unique[key] = state
    ordered = list(unique.values())
    if not ordered:
        return []
    if len({(state.day, state.node, state.finished) for state in ordered}) > 1:
        survivors: list[PlayerState] = []
        for state in sorted(ordered, key=lambda s: (s.day, s.node, s.finished, s.cash, s.water, s.food), reverse=True):
            if any(dominates(existing, state) for existing in survivors):
                continue
            survivors.append(state)
        return survivors

    max_water = max(state.water for state in ordered)
    tree = [-1] * (max_water + 3)

    def query(idx: int) -> int:
        best = -1
        while idx > 0:
            if tree[idx] > best:
                best = tree[idx]
            idx -= idx & -idx
        return best

    def update(idx: int, value: int) -> None:
        while idx < len(tree):
            if value > tree[idx]:
                tree[idx] = value
            idx += idx & -idx

    survivors: list[PlayerState] = []
    for state in sorted(ordered, key=lambda s: (s.cash, s.water, s.food), reverse=True):
        # Fenwick prefix max over reversed water index answers:
        # among accepted states with water >= current water, what is max food?
        reversed_water = max_water - state.water + 1
        if query(reversed_water) >= state.food:
            continue
        survivors.append(state)
        update(reversed_water, state.food)
    return survivors


def multiplayer_multiplier(formula: str, same_group_count: int, base_multiplier: float) -> float:
    """Evaluate supported multiplayer formulas.

    The official problem uses MathType expressions that must be reviewed from the
    source document. This helper intentionally supports only explicit formulas
    recorded in config; unknown formulas fail loudly.
    """

    if same_group_count <= 0:
        raise ValueError("same_group_count must be positive")
    if formula in ("single", "base"):
        return base_multiplier
    if formula == "pending_review":
        raise ValueError("multiplayer formula is pending review")
    if formula == "base_plus_k":
        return base_multiplier + same_group_count
    if formula == "base_times_k":
        return base_multiplier * same_group_count
    if formula == "multiplier_2k":
        return 2 * same_group_count
    if formula == "base_div_k":
        return base_multiplier / same_group_count
    if formula in ("fixed_4", "base_price_times_4", "base_times_4"):
        return 4
    raise ValueError("Unsupported multiplayer formula: %s" % formula)
