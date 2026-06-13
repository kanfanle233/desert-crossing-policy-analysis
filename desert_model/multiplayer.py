"""Multiplayer strategy scaffolding for levels 5 and 6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .models import LevelConfig
from .rules import multiplayer_multiplier
from .validate import validate_level


@dataclass(frozen=True)
class MultiplayerEffect:
    same_group_count: int
    move_multiplier: float
    mine_multiplier: float
    income_multiplier: float
    village_price_multiplier: float


def multiplayer_preconditions(level: LevelConfig) -> List[str]:
    issues = validate_level(level, require_graph=True)
    if level.players is None:
        issues.append("players is missing")
    if level.rules.multiplayer_move_formula == "pending_review":
        issues.append("multiplayer_move_formula is pending_review")
    if level.rules.multiplayer_mine_formula == "pending_review":
        issues.append("multiplayer_mine_formula is pending_review")
    if level.rules.multiplayer_income_formula == "pending_review":
        issues.append("multiplayer_income_formula is pending_review")
    if level.rules.multiplayer_village_price_formula == "pending_review":
        issues.append("multiplayer_village_price_formula is pending_review")
    return sorted(set(issues))


def compute_effect_table(level: LevelConfig) -> List[MultiplayerEffect]:
    issues = multiplayer_preconditions(level)
    if issues:
        raise ValueError("; ".join(issues))
    assert level.players is not None
    rows: List[MultiplayerEffect] = []
    for count in range(1, level.players + 1):
        rows.append(
            MultiplayerEffect(
                same_group_count=count,
                move_multiplier=multiplayer_multiplier(
                    level.rules.multiplayer_move_formula,
                    count,
                    level.rules.move_multiplier,
                ),
                mine_multiplier=multiplayer_multiplier(
                    level.rules.multiplayer_mine_formula,
                    count,
                    level.rules.mine_multiplier,
                ),
                income_multiplier=multiplayer_multiplier(
                    level.rules.multiplayer_income_formula,
                    count,
                    1.0,
                ),
                village_price_multiplier=multiplayer_multiplier(
                    level.rules.multiplayer_village_price_formula,
                    count,
                    level.rules.village_price_multiplier,
                ),
            )
        )
    return rows


def multiplayer_strategy_summary(level: LevelConfig) -> Dict[str, object]:
    issues = multiplayer_preconditions(level)
    if issues:
        return {
            "ready": False,
            "issues": issues,
            "recommended_model": "先复核玩家数、地图邻接和多人交互公式，再做合作总收益最大化与个体偏离收益检查。",
        }
    table = compute_effect_table(level)
    return {
        "ready": True,
        "issues": [],
        "effect_table": [row.__dict__ for row in table],
        "recommended_model": "用合作策略生成候选联合行动，再用每日滚动重优化处理第六关信息更新。",
    }
