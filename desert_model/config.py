"""Configuration loading and default level data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

from .models import (
    LevelConfig,
    ResourceSpec,
    RuleConfig,
    ensure_weather_sequence,
    parse_int_tuple,
)
from .maps import BUILTIN_MAP_NOTE, builtin_adjacency


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "levels.json"


def _resource_from_dict(name: str, payload: Mapping[str, Any]) -> ResourceSpec:
    return ResourceSpec(
        name=name,
        mass_kg=int(payload["mass_kg"]),
        base_price=int(payload["base_price"]),
        base_consumption={str(k): int(v) for k, v in payload["base_consumption"].items()},
    )


def _rules_from_dict(payload: Optional[Mapping[str, Any]]) -> RuleConfig:
    if not payload:
        return RuleConfig()
    base = RuleConfig()
    data = base.__dict__.copy()
    data.update(payload)
    return RuleConfig(**data)


def _adjacency_from_dict(payload: Optional[Mapping[str, Iterable[Any]]]) -> Dict[int, tuple[int, ...]]:
    if not payload:
        return {}
    return {int(node): tuple(sorted(int(n) for n in nbrs)) for node, nbrs in payload.items()}


def level_from_dict(payload: Mapping[str, Any]) -> LevelConfig:
    resources = {
        name: _resource_from_dict(name, spec)
        for name, spec in payload["resources"].items()
    }
    adjacency = _adjacency_from_dict(payload.get("adjacency"))
    if not adjacency:
        adjacency = builtin_adjacency(int(payload["level_id"]))
    notes = tuple(str(item) for item in payload.get("notes", []))
    if adjacency and BUILTIN_MAP_NOTE not in notes:
        notes = notes + (BUILTIN_MAP_NOTE,)
    return LevelConfig(
        level_id=int(payload["level_id"]),
        name=str(payload["name"]),
        deadline=int(payload["deadline"]),
        carry_limit_kg=int(payload["carry_limit_kg"]),
        initial_cash=int(payload["initial_cash"]),
        base_income=int(payload["base_income"]),
        resources=resources,
        start_node=int(payload["start_node"]),
        goal_node=int(payload["goal_node"]),
        mines=parse_int_tuple(payload.get("mines", [])),
        villages=parse_int_tuple(payload.get("villages", [])),
        weather=ensure_weather_sequence(payload.get("weather")),
        weather_policy=dict(payload.get("weather_policy", {})),
        adjacency=adjacency,
        rules=_rules_from_dict(payload.get("rules")),
        players=int(payload["players"]) if payload.get("players") is not None else None,
        review_required=bool(payload.get("review_required", False)),
        notes=notes,
    )


def level_to_dict(level: LevelConfig) -> Dict[str, Any]:
    return {
        "level_id": level.level_id,
        "name": level.name,
        "deadline": level.deadline,
        "carry_limit_kg": level.carry_limit_kg,
        "initial_cash": level.initial_cash,
        "base_income": level.base_income,
        "resources": {
            key: {
                "mass_kg": spec.mass_kg,
                "base_price": spec.base_price,
                "base_consumption": dict(spec.base_consumption),
            }
            for key, spec in level.resources.items()
        },
        "start_node": level.start_node,
        "goal_node": level.goal_node,
        "mines": list(level.mines),
        "villages": list(level.villages),
        "weather": list(level.weather) if level.weather else None,
        "weather_policy": dict(level.weather_policy),
        "adjacency": {str(k): list(v) for k, v in level.adjacency.items()},
        "rules": level.rules.__dict__.copy(),
        "players": level.players,
        "review_required": level.review_required,
        "notes": list(level.notes),
    }


def load_levels(path: Optional[Path] = None) -> List[LevelConfig]:
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    raw_levels = payload.get("levels", payload)
    return [level_from_dict(item) for item in raw_levels]


def load_level_map(path: Optional[Path] = None) -> Dict[int, LevelConfig]:
    levels = load_levels(path)
    return {level.level_id: level for level in levels}


def save_levels(levels: Iterable[LevelConfig], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"levels": [level_to_dict(level) for level in levels]}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def select_levels(levels: Mapping[int, LevelConfig], spec: str) -> List[LevelConfig]:
    if spec.strip().lower() == "all":
        return [levels[key] for key in sorted(levels)]
    selected: List[LevelConfig] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        level_id = int(part)
        if level_id not in levels:
            raise KeyError("Unknown level id %s" % level_id)
        selected.append(levels[level_id])
    return selected


def default_output_root(root: Optional[Path] = None) -> Path:
    return Path(root or PROJECT_ROOT / "output")
