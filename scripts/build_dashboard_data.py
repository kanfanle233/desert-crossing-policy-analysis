#!/usr/bin/env python3
"""Generate dashboard data payload from local outputs."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_payload():
    payload = {"generated": "2026-06-12", "levels": {}}

    # Load configs
    configs = load_json(ROOT / "configs" / "levels.json")
    for lv in configs["levels"]:
        lid = lv["level_id"]
        payload["levels"][lid] = {
            "config": {
                "level_id": lid,
                "name": lv["name"],
                "deadline": lv["deadline"],
                "carry_limit_kg": lv["carry_limit_kg"],
                "initial_cash": lv["initial_cash"],
                "base_income": lv["base_income"],
                "start_node": lv["start_node"],
                "goal_node": lv["goal_node"],
                "mines": lv["mines"],
                "villages": lv["villages"],
                "weather": lv.get("weather"),
                "weather_policy": lv.get("weather_policy", {}),
                "rules": lv["rules"],
                "players": lv.get("players"),
            }
        }

    # Load level 1/2 traces
    for lid in [1, 2]:
        trace_path = ROOT / "output" / "solutions" / f"level_{lid}_trace.json"
        if trace_path.exists():
            trace = load_json(trace_path)
            payload["levels"][lid]["trace"] = {
                "objective_value": trace["objective_value"],
                "feasible": trace["feasible"],
                "status": trace["status"],
                "rows": trace["rows"],
                "metadata": trace.get("metadata", {}),
            }

    # Load analysis summary (levels 3-6)
    analysis_path = ROOT / "output" / "report_tables" / "analysis_summary.json"
    if analysis_path.exists():
        analysis = load_json(analysis_path)
        for report in analysis:
            lid = report["level_id"]
            if lid in payload["levels"]:
                payload["levels"][lid]["analysis"] = {
                    "strategy": report.get("strategy", ""),
                    "scenario_count": report.get("scenario_count", 0),
                    "feasible_scenarios": report.get("feasible_scenarios", 0),
                    "best_objective": report.get("best_objective"),
                    "worst_objective": report.get("worst_objective"),
                    "failure_rate": report.get("failure_rate"),
                    "rolling_strategy": report.get("rolling_strategy"),
                    "cooperative_analysis": report.get("cooperative_analysis"),
                    "grouping_scenarios": report.get("grouping_scenarios"),
                    "deviation_analysis": report.get("deviation_analysis"),
                    "sensitivity_by_storm_count": report.get("sensitivity_by_storm_count"),
                    "single_player_objective": report.get("single_player_objective"),
                    "multiplayer": report.get("multiplayer"),
                }

    # Load adjacency from maps.py
    from desert_model.maps import BUILTIN_ADJACENCY
    for lid, adj in BUILTIN_ADJACENCY.items():
        if lid in payload["levels"]:
            payload["levels"][lid]["adjacency"] = {str(k): list(v) for k, v in adj.items()}

    return payload


if __name__ == "__main__":
    payload = build_payload()
    out_path = ROOT / "output" / "frontend" / "dashboard-data.js"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("// Auto-generated from local outputs — do not edit manually\n")
        f.write("const DASHBOARD_DATA = ")
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print(f"Written: {out_path} ({out_path.stat().st_size} bytes)")
