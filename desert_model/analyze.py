"""Scenario analysis and report-table generation."""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from .baseline import baseline_shortest_path_trace
from .models import LevelConfig, SolutionTrace, WEATHER_HOT, WEATHER_STORM, WEATHER_SUNNY
from .multiplayer import multiplayer_strategy_summary
from .solver import solve_deterministic_level
from .validate import validate_level, validate_trace


def generate_weather_scenarios(level: LevelConfig, limit: int = 200) -> List[Sequence[str]]:
    policy = dict(level.weather_policy)
    if level.weather:
        return [level.weather]
    allowed = policy.get("allowed", [WEATHER_SUNNY, WEATHER_HOT, WEATHER_STORM])
    max_storm = policy.get("max_storm_days")
    scenarios: List[Sequence[str]] = []
    for combo in itertools.product(allowed, repeat=level.deadline):
        if max_storm is not None and combo.count(WEATHER_STORM) > int(max_storm):
            continue
        scenarios.append(combo)
        if len(scenarios) >= limit:
            break
    return scenarios


def _compute_rolling_strategy(level: LevelConfig, weather: Sequence[str], ignore_review: bool = False) -> Dict:
    """Compute a rolling strategy: follow shortest path, adapt to weather."""
    from .baseline import shortest_path
    from .models import PlayerState
    from .rules import daily_consumption, purchase_options, terminal_value, carried_weight

    path = shortest_path(level)
    if not path:
        return {"feasible": False, "steps": [], "objective": None}

    state = PlayerState(0, level.start_node, level.initial_cash, 0, 0, False)
    trace_steps = [{"day": 0, "node": state.node, "cash": state.cash, "water": state.water, "food": state.food, "action": "initial"}]

    # Compute total resource needs for the path
    total_water = 0
    total_food = 0
    path_idx = 0
    for day_i in range(len(weather)):
        if path_idx >= len(path) - 1:
            break
        w = weather[day_i]
        if w == WEATHER_STORM:
            mult = level.rules.stay_multiplier
        else:
            mult = level.rules.move_multiplier
            path_idx += 1
        c_water, c_food = daily_consumption(level, w, mult)
        total_water += c_water
        total_food += c_food

    # Buy enough resources at start
    cost = total_water * level.resources["water"].base_price * level.rules.start_price_multiplier + total_food * level.resources["food"].base_price * level.rules.start_price_multiplier
    if cost > level.initial_cash or carried_weight(level, total_water, total_food) > level.carry_limit_kg:
        # Reduce to fit
        max_water = level.carry_limit_kg // level.resources["water"].mass_kg
        total_water = min(total_water, max_water)
        total_food = min(total_food, (level.carry_limit_kg - total_water * level.resources["water"].mass_kg) // level.resources["food"].mass_kg)

    state = PlayerState(0, level.start_node, level.initial_cash - int(cost), total_water, total_food, False)
    trace_steps = [{"day": 0, "node": state.node, "cash": state.cash, "water": state.water, "food": state.food, "action": "buy_start"}]

    path_idx = 0
    for day_i in range(len(weather)):
        w = weather[day_i]
        if state.finished:
            break

        if w == WEATHER_STORM or path_idx >= len(path) - 1:
            kind, to_node = "stay", state.node
            mult = level.rules.stay_multiplier
        else:
            next_node = path[path_idx + 1]
            kind, to_node = "move", next_node
            mult = level.rules.move_multiplier
            path_idx += 1

        c_water, c_food = daily_consumption(level, w, mult)
        income = level.base_income if kind == "mine" and state.node in level.mines else 0
        next_water = state.water - c_water
        next_food = state.food - c_food
        next_cash = state.cash + income

        if next_water < 0 or next_food < 0:
            trace_steps.append({"day": day_i + 1, "node": state.node, "cash": state.cash, "water": state.water, "food": state.food, "action": "infeasible"})
            return {"feasible": False, "steps": trace_steps, "objective": None}

        finished = to_node == level.goal_node
        state = PlayerState(day_i + 1, to_node, next_cash, next_water, next_food, finished)
        trace_steps.append({"day": day_i + 1, "node": state.node, "cash": state.cash, "water": state.water, "food": state.food, "action": kind})

    obj = terminal_value(level, state) if state.finished else None
    return {"feasible": state.finished, "steps": trace_steps, "objective": obj}


def _compute_cooperative_payoff(level: LevelConfig, n_players: int, weather: Sequence[str]) -> Dict:
    """Compute cooperative strategy payoff: all n players follow the same path."""
    from .models import PlayerState
    from .rules import daily_consumption, purchase_options, terminal_value, carried_weight

    # Known-weather multiplayer levels can reuse the deterministic search. For
    # sampled unknown-weather levels, use the baseline route to keep scenario
    # analysis bounded and reproducible.
    if level.has_known_weather:
        single_trace = solve_deterministic_level(
            level,
            weather_sequence=tuple(weather),
            ignore_review=True,
            max_states_per_bucket=300,
            max_purchase_options=200,
            purchase_step=25,
        )
    else:
        single_trace = baseline_shortest_path_trace(level, weather_sequence=tuple(weather))
    if not single_trace.feasible:
        return {"feasible": False, "single_objective": None, "cooperative_total": None, "per_player": None}

    single_obj = single_trace.objective_value

    # Now simulate n players following the same actions with multiplayer multipliers
    from .multiplayer import compute_effect_table
    effect_table = compute_effect_table(level)
    k = n_players  # all together
    effect = effect_table[k - 1]  # 0-indexed

    # Re-simulate with multiplayer multipliers
    state = PlayerState(0, level.start_node, level.initial_cash, 0, 0, False)
    # Initial purchase (same price for start)
    for opt in purchase_options(level, state, level.rules.start_price_multiplier, max_options=200, step=25):
        if opt.water > 0 and opt.food > 0 and carried_weight(level, opt.water, opt.food) <= level.carry_limit_kg:
            state = opt
            break

    for step in single_trace.steps[1:]:  # skip initial
        action = step.action
        if action is None:
            continue
        w = action.weather or (weather[step.day - 1] if step.day > 0 and step.day <= len(weather) else "晴朗")

        if action.kind == "move":
            mult = effect.move_multiplier
        elif action.kind == "mine":
            mult = effect.mine_multiplier
        elif action.kind == "stay":
            mult = level.rules.stay_multiplier
        else:
            continue

        c_water, c_food = daily_consumption(level, w, mult)
        income = int(level.base_income * effect.income_multiplier) if action.kind == "mine" else 0
        next_water = state.water - c_water
        next_food = state.food - c_food
        next_cash = state.cash + income

        if next_water < 0 or next_food < 0:
            return {"feasible": False, "single_objective": single_obj, "cooperative_total": None,
                    "failure_reason": f"resource exhaustion at day {step.day} with k={k}"}

        finished = action.to_node == level.goal_node
        state = PlayerState(step.day, action.to_node, next_cash, next_water, next_food, finished)

        # Village purchase
        if action.to_node in level.villages and not finished:
            for opt in purchase_options(level, state, effect.village_price_multiplier, max_options=200, step=25):
                if carried_weight(level, opt.water, opt.food) <= level.carry_limit_kg:
                    state = opt
                    break

    if state.finished:
        per_player = terminal_value(level, state)
        total = per_player * n_players
        return {"feasible": True, "single_objective": single_obj,
                "cooperative_total": total, "per_player": per_player,
                "deviation_check": per_player >= single_obj * 0.5}  # rough check
    return {"feasible": False, "single_objective": single_obj, "cooperative_total": None,
            "failure_reason": "did not reach goal"}


def analyze_level(level: LevelConfig, output_dir: Path, ignore_review: bool = False) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, object] = {
        "level_id": level.level_id,
        "name": level.name,
        "config_issues": validate_level(level, require_graph=False),
        "strategy": "",
        "scenario_count": 0,
        "feasible_scenarios": 0,
        "best_objective": None,
        "worst_objective": None,
        "notes": list(level.notes),
    }
    if level.level_id in (5, 6):
        multiplayer = multiplayer_strategy_summary(level)
        if not multiplayer.get("ready"):
            report["strategy"] = (
                "多人关卡的后端接口已就绪；需要先复核玩家数和多人函数，"
                "再调用合作策略/滚动策略求解。"
            )
            report["multiplayer"] = multiplayer
            return report
        report["multiplayer"] = multiplayer
        n = level.players or 4
        effect_table = multiplayer.get("effect_table", [])

        # Generate grouping scenarios
        groupings = []
        if n == 2:
            groupings = [
                {"label": "all_together", "groups": [[1,2]], "description": "2 人全程同行同矿同村"},
                {"label": "all_solo", "groups": [[1],[2]], "description": "2 人各自独立"},
            ]
        elif n == 3:
            groupings = [
                {"label": "all_together", "groups": [[1,2,3]], "description": "3 人全程同行同矿同村"},
                {"label": "pair_plus_solo", "groups": [[1,2],[3]], "description": "2+1 分组"},
                {"label": "all_solo", "groups": [[1],[2],[3]], "description": "3 人各自独立"},
            ]
        elif n == 4:
            groupings = [
                {"label": "all_together", "groups": [[1,2,3,4]], "description": "4 人全程同行同矿同村"},
                {"label": "two_pairs", "groups": [[1,2],[3,4]], "description": "2+2 分组"},
                {"label": "one_trio_one_solo", "groups": [[1,2,3],[4]], "description": "3+1 分组"},
                {"label": "all_solo", "groups": [[1],[2],[3],[4]], "description": "4 人各自独立"},
            ]
        else:
            groupings = [{"label": "all_together", "groups": [list(range(1, n+1))], "description": f"{n} 人全程同行"}]

        grouping_results = []
        for grouping in groupings:
            result = {
                "label": grouping["label"],
                "description": grouping["description"],
                "group_sizes": [len(g) for g in grouping["groups"]],
                "multiplier_summary": [],
            }
            for group in grouping["groups"]:
                k = len(group)
                effect = next((e for e in effect_table if e["same_group_count"] == k), None)
                if effect:
                    result["multiplier_summary"].append({
                        "k": k,
                        "move_multiplier": effect["move_multiplier"],
                        "mine_multiplier": effect["mine_multiplier"],
                        "income_multiplier": effect["income_multiplier"],
                        "village_price_multiplier": effect["village_price_multiplier"],
                    })
            grouping_results.append(result)
        report["grouping_scenarios"] = grouping_results

        # Compute cooperative strategy for "all_together" grouping
        weather_seq = level.weather
        if weather_seq:
            coop = _compute_cooperative_payoff(level, n, tuple(weather_seq))
            report["cooperative_analysis"] = coop
        else:
            # For unknown weather, sample scenarios
            scenarios = generate_weather_scenarios(level, limit=10)
            coop_results = []
            for w in scenarios:
                coop = _compute_cooperative_payoff(level, n, tuple(w))
                coop_results.append(coop)
            feasible_coops = [c for c in coop_results if c.get("feasible")]
            if feasible_coops:
                report["cooperative_analysis"] = {
                    "feasible_count": len(feasible_coops),
                    "total_scenarios": len(coop_results),
                    "best_cooperative_total": max(c["cooperative_total"] for c in feasible_coops),
                    "worst_cooperative_total": min(c["cooperative_total"] for c in feasible_coops),
                    "best_per_player": max(c["per_player"] for c in feasible_coops),
                    "worst_per_player": min(c["per_player"] for c in feasible_coops),
                    "failure_rate": 1 - len(feasible_coops) / len(coop_results),
                }
            else:
                total = len(coop_results)
                report["cooperative_analysis"] = {
                    "feasible_count": 0,
                    "total_scenarios": total,
                    "failure_rate": 1.0 if total else 0.0,
                }

        # Compute single-player baseline
        if weather_seq:
            single_trace = solve_deterministic_level(
                level, weather_sequence=tuple(weather_seq), ignore_review=True,
                max_states_per_bucket=500, max_purchase_options=300, purchase_step=25,
            )
            single_obj = single_trace.objective_value if single_trace.feasible else None
        else:
            scenarios = generate_weather_scenarios(level, limit=10)
            single_obj = None
            for w in scenarios:
                t = baseline_shortest_path_trace(level, weather_sequence=tuple(w))
                if t.feasible:
                    if single_obj is None or t.objective_value > single_obj:
                        single_obj = t.objective_value
        report["single_player_objective"] = single_obj

        # Deviation analysis
        coop_data = report.get("cooperative_analysis", {})
        if isinstance(coop_data, dict) and coop_data.get("feasible"):
            per_player = coop_data.get("per_player", 0)
            report["deviation_analysis"] = {
                "cooperative_per_player": per_player,
                "single_player_optimal": single_obj,
                "cooperation_beneficial": per_player > (single_obj or 0) * 0.5,
                "note": "单人独立行动时每人收益约等于单人最优；合作时消耗增加但可以互相支援。",
            }
        else:
            report["deviation_analysis"] = {"note": "合作策略不可行或数据不足，无法计算偏离收益。"}

        if level.level_id == 5:
            report["strategy"] = (
                "第五关：%d 名玩家，已知天气，合作策略。" % n
                + "单人最优目标值=%s。" % single_obj
                + "已计算合作策略收益和偏离检查。"
                + "已生成 %d 种分组方案的参数对比。" % len(grouping_results)
            )
        else:
            report["strategy"] = (
                "第六关：%d 名玩家，未知天气，滚动策略。" % n
                + "单人最优目标值=%s（基于采样场景）。" % single_obj
                + "已计算合作策略收益、失败率和偏离检查。"
                + "已生成 %d 种分组方案的参数对比。" % len(grouping_results)
            )
        return report

    # Levels 1-4: standard analysis
    scenarios = generate_weather_scenarios(level, limit=40)
    report["scenario_count"] = len(scenarios)
    rows = []
    objectives = []
    for idx, weather in enumerate(scenarios, 1):
        if level.has_known_weather:
            trace = solve_deterministic_level(
                level, weather, ignore_review=ignore_review,
                max_states_per_bucket=500, max_purchase_options=300, purchase_step=25,
            )
        else:
            trace = baseline_shortest_path_trace(level, weather_sequence=tuple(weather))
        feasible = trace.feasible
        objective = trace.objective_value if feasible else None
        if feasible:
            objectives.append(trace.objective_value)
        rows.append(
            {
                "scenario": idx,
                "weather": "".join(weather),
                "feasible": feasible,
                "objective": objective,
                "arrival_day": trace.final_state().day if trace.final_state() else None,
                "status": trace.status,
                "message": trace.message,
            }
        )
    csv_path = output_dir / ("level_%s_scenarios.csv" % level.level_id)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scenario", "weather", "feasible", "objective", "arrival_day", "status", "message"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    report["feasible_scenarios"] = len(objectives)
    total_scenarios = len(scenarios)
    report["failure_rate"] = 1 - len(objectives) / total_scenarios if total_scenarios > 0 else 0
    if objectives:
        report["best_objective"] = max(objectives)
        report["worst_objective"] = min(objectives)
        report["mean_objective"] = sum(objectives) / len(objectives)
        # Sensitivity analysis: vary storm count
        if not level.has_known_weather:
            sensitivity = {}
            for storm_count in range(0, (level.weather_policy.get("max_storm_days", 0) or 0) + 1):
                storm_scenarios = [s for s in scenarios if s.count(WEATHER_STORM) == storm_count]
                storm_objs = []
                for w in storm_scenarios:
                    t = baseline_shortest_path_trace(level, weather_sequence=tuple(w))
                    if t.feasible:
                        storm_objs.append(t.objective_value)
                if storm_objs:
                    sensitivity[f"{storm_count}_storms"] = {
                        "count": len(storm_scenarios),
                        "feasible": len(storm_objs),
                        "best": max(storm_objs),
                        "worst": min(storm_objs),
                    }
            report["sensitivity_by_storm_count"] = sensitivity
        # Rolling strategy for levels 3/4 (sample one scenario)
        if level.has_known_weather:
            rolling = _compute_rolling_strategy(level, level.weather, ignore_review=ignore_review)
        else:
            rolling = _compute_rolling_strategy(level, scenarios[0] if scenarios else ["晴朗"] * level.deadline)
        report["rolling_strategy"] = {
            "feasible": rolling["feasible"],
            "objective": rolling["objective"],
            "steps_sample": rolling["steps"][:5],  # first 5 days
        }
        report["strategy"] = (
            "按场景集合做稳健比较，优先选择最坏收益较高且失败率较低的策略。"
            "失败率=%.1f%%，最优=%.0f，最差=%.0f。" % (
                report["failure_rate"] * 100, report["best_objective"], report["worst_objective"]
            )
        )
    else:
        report["strategy"] = "当前场景集合下未找到可行策略。"
    report["scenario_table"] = str(csv_path)
    return report


def write_analysis_report(levels: Iterable[LevelConfig], output_dir: Path, ignore_review: bool = False) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = [analyze_level(level, output_dir, ignore_review=ignore_review) for level in levels]
    json_path = output_dir / "analysis_summary.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(reports, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    md_path = output_dir / "analysis_summary.md"
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# 穿越沙漠策略分析摘要\n\n")
        for report in reports:
            handle.write("## 第%s关 %s\n" % (report["level_id"], report["name"]))
            handle.write("- 策略说明：%s\n" % report["strategy"])
            if report["level_id"] in (5, 6):
                handle.write("- 分组方案数：%s\n" % len(report.get("grouping_scenarios") or []))
                if report.get("single_player_objective") is not None:
                    handle.write("- 单人参考目标：%s\n" % report["single_player_objective"])
            else:
                handle.write("- 场景数：%s，可行场景：%s\n" % (report["scenario_count"], report["feasible_scenarios"]))
                handle.write("- 最优目标：%s，最差目标：%s\n" % (report["best_objective"], report["worst_objective"]))
            if report.get("failure_rate") is not None:
                handle.write("- 失败率：%.1f%%\n" % (report["failure_rate"] * 100))
            if report.get("rolling_strategy"):
                rs = report["rolling_strategy"]
                handle.write("- 滚动策略：可行=%s，目标值=%s\n" % (rs["feasible"], rs["objective"]))
            if report.get("cooperative_analysis"):
                ca = report["cooperative_analysis"]
                if ca.get("feasible"):
                    handle.write("- 合作策略：每人收益=%.0f，总收益=%.0f\n" % (ca["per_player"], ca["cooperative_total"]))
                elif ca.get("feasible_count") is not None:
                    handle.write("- 合作策略：可行场景=%d/%d，失败率=%.1f%%\n" % (
                        ca["feasible_count"], ca["total_scenarios"],
                        ca.get("failure_rate", 0) * 100))
                elif ca.get("feasible") is False:
                    handle.write("- 合作策略：可行=False，原因=%s\n" % ca.get("failure_reason"))
            if report.get("deviation_analysis"):
                da = report["deviation_analysis"]
                if isinstance(da, dict) and da.get("cooperative_per_player"):
                    handle.write("- 偏离检查：合作每人=%.0f，单人最优=%.0f，合作有利=%s\n" % (
                        da["cooperative_per_player"], da.get("single_player_optimal", 0),
                        da.get("cooperation_beneficial")))
            issues = report.get("config_issues") or []
            if issues:
                handle.write("- 配置问题：%s\n" % "；".join(str(i) for i in issues))
            handle.write("\n")
    return json_path
