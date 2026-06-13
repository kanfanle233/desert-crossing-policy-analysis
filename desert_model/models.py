"""Core data structures for desert crossing optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


WEATHER_SUNNY = "晴朗"
WEATHER_HOT = "高温"
WEATHER_STORM = "沙暴"
WEATHERS = (WEATHER_SUNNY, WEATHER_HOT, WEATHER_STORM)

RESOURCE_WATER = "water"
RESOURCE_FOOD = "food"
RESOURCES = (RESOURCE_WATER, RESOURCE_FOOD)


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    mass_kg: int
    base_price: int
    base_consumption: Mapping[str, int]

    def consumption(self, weather: str, multiplier: float = 1.0) -> int:
        return int(round(self.base_consumption[weather] * multiplier))


@dataclass(frozen=True)
class RuleConfig:
    stay_multiplier: float = 1.0
    move_multiplier: float = 2.0
    mine_multiplier: float = 3.0
    start_price_multiplier: float = 1.0
    village_price_multiplier: float = 2.0
    refund_multiplier: float = 0.5
    multiplayer_move_formula: str = "pending_review"
    multiplayer_mine_formula: str = "pending_review"
    multiplayer_income_formula: str = "pending_review"
    multiplayer_village_price_formula: str = "pending_review"


@dataclass(frozen=True)
class LevelConfig:
    level_id: int
    name: str
    deadline: int
    carry_limit_kg: int
    initial_cash: int
    base_income: int
    resources: Mapping[str, ResourceSpec]
    start_node: int
    goal_node: int
    mines: Tuple[int, ...] = ()
    villages: Tuple[int, ...] = ()
    weather: Optional[Tuple[str, ...]] = None
    weather_policy: Mapping[str, Any] = field(default_factory=dict)
    adjacency: Mapping[int, Tuple[int, ...]] = field(default_factory=dict)
    rules: RuleConfig = field(default_factory=RuleConfig)
    players: Optional[int] = None
    review_required: bool = True
    notes: Tuple[str, ...] = ()

    @property
    def has_known_weather(self) -> bool:
        return self.weather is not None and len(self.weather) == self.deadline

    @property
    def has_reviewed_graph(self) -> bool:
        return bool(self.adjacency) and not self.review_required

    def neighbors(self, node: int) -> Tuple[int, ...]:
        return tuple(self.adjacency.get(node, ()))

    def all_nodes(self) -> Tuple[int, ...]:
        nodes = {self.start_node, self.goal_node, *self.mines, *self.villages}
        for node, nbrs in self.adjacency.items():
            nodes.add(int(node))
            nodes.update(int(n) for n in nbrs)
        return tuple(sorted(nodes))


@dataclass(frozen=True)
class PlayerState:
    day: int
    node: int
    cash: int
    water: int
    food: int
    finished: bool = False

    def resource_tuple(self) -> Tuple[int, int]:
        return self.water, self.food

    def with_day(self, day: int) -> "PlayerState":
        return PlayerState(day, self.node, self.cash, self.water, self.food, self.finished)


@dataclass(frozen=True)
class Action:
    kind: str
    from_node: int
    to_node: int
    weather: Optional[str] = None
    buy_water: int = 0
    buy_food: int = 0
    consume_water: int = 0
    consume_food: int = 0
    income: int = 0
    note: str = ""


@dataclass
class TraceStep:
    day: int
    state: PlayerState
    action: Optional[Action] = None


@dataclass
class SolutionTrace:
    level_id: int
    objective_value: float
    feasible: bool
    steps: List[TraceStep] = field(default_factory=list)
    status: str = "ok"
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def final_state(self) -> Optional[PlayerState]:
        if not self.steps:
            return None
        return self.steps[-1].state

    def to_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for step in self.steps:
            action = step.action
            rows.append(
                {
                    "day": step.day,
                    "node": step.state.node,
                    "cash": step.state.cash,
                    "water": step.state.water,
                    "food": step.state.food,
                    "finished": step.state.finished,
                    "action": action.kind if action else "initial",
                    "from_node": action.from_node if action else None,
                    "to_node": action.to_node if action else step.state.node,
                    "weather": action.weather if action else None,
                    "buy_water": action.buy_water if action else 0,
                    "buy_food": action.buy_food if action else 0,
                    "consume_water": action.consume_water if action else 0,
                    "consume_food": action.consume_food if action else 0,
                    "income": action.income if action else 0,
                    "note": action.note if action else "",
                }
            )
        return rows


def parse_int_tuple(values: Iterable[Any]) -> Tuple[int, ...]:
    return tuple(int(v) for v in values)


def sorted_adjacency(edges: Iterable[Tuple[int, int]]) -> Dict[int, Tuple[int, ...]]:
    graph: Dict[int, set[int]] = {}
    for left, right in edges:
        if left == right:
            continue
        graph.setdefault(int(left), set()).add(int(right))
        graph.setdefault(int(right), set()).add(int(left))
    return {node: tuple(sorted(nbrs)) for node, nbrs in sorted(graph.items())}


def ensure_weather_sequence(values: Optional[Sequence[str]]) -> Optional[Tuple[str, ...]]:
    if values is None:
        return None
    cleaned = tuple(str(v) for v in values)
    bad = [v for v in cleaned if v not in WEATHERS]
    if bad:
        raise ValueError("Unknown weather values: %s" % ", ".join(sorted(set(bad))))
    return cleaned
