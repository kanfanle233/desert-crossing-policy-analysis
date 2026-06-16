"""Generate saved figures and a static frontend dashboard."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib_desert")

from .config import load_level_map
from .models import SolutionTrace


LEVEL1_POSITIONS = {
    1: (5.285, -1.526),
    2: (4.689, -2.208),
    3: (4.966, -2.943),
    4: (5.740, -3.020),
    5: (5.936, -4.014),
    6: (6.883, -4.443),
    7: (7.112, -4.867),
    8: (7.228, -5.542),
    9: (8.042, -5.808),
    10: (7.350, -6.971),
    11: (7.350, -7.879),
    12: (8.494, -8.196),
    13: (7.910, -7.762),
    14: (8.500, -7.762),
    15: (8.224, -6.891),
    16: (9.203, -6.841),
    17: (8.994, -5.635),
    18: (9.606, -5.635),
    19: (10.139, -5.241),
    20: (9.869, -4.926),
    21: (9.117, -4.014),
    22: (7.964, -4.761),
    23: (7.902, -3.683),
    24: (7.100, -3.362),
    25: (6.265, -2.019),
    26: (7.948, -2.028),
    27: (8.940, -1.990),
}


def level2_positions() -> Dict[int, Tuple[float, float]]:
    positions = {}
    for node in range(1, 65):
        row = (node - 1) // 8
        col = (node - 1) % 8
        positions[node] = (col + 0.5 * (row % 2), -row)
    return positions


def read_trace(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rows(trace: Mapping[str, object]) -> List[Mapping[str, object]]:
    return list(trace.get("rows", []))  # type: ignore[arg-type]


def generate_resource_figure(trace: Mapping[str, object], path: Path) -> None:
    import matplotlib.pyplot as plt

    rows = _rows(trace)
    days = [row["day"] for row in rows]
    water = [row["water"] for row in rows]
    food = [row["food"] for row in rows]
    cash = [row["cash"] for row in rows]
    fig, ax1 = plt.subplots(figsize=(8, 4.6), dpi=160)
    ax1.plot(days, water, marker="o", label="Water boxes", color="#1f77b4")
    ax1.plot(days, food, marker="o", label="Food boxes", color="#2ca02c")
    ax1.set_xlabel("Day")
    ax1.set_ylabel("Resource boxes")
    ax1.grid(True, alpha=0.25)
    ax2 = ax1.twinx()
    ax2.plot(days, cash, marker="s", label="Cash", color="#d62728")
    ax2.set_ylabel("Cash")
    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="best")
    ax1.set_title("Level %s resource and cash trajectory" % trace["level_id"])
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def generate_path_figure(level_id: int, trace: Mapping[str, object], path: Path) -> None:
    import matplotlib.pyplot as plt

    levels = load_level_map()
    level = levels[level_id]
    positions = LEVEL1_POSITIONS if level_id == 1 else level2_positions()
    route = [int(row["node"]) for row in _rows(trace)]
    fig, ax = plt.subplots(figsize=(8, 6), dpi=160)
    for node, neighbors in level.adjacency.items():
        x1, y1 = positions.get(node, (None, None))
        if x1 is None:
            continue
        for neighbor in neighbors:
            if neighbor < node:
                continue
            x2, y2 = positions.get(neighbor, (None, None))
            if x2 is None:
                continue
            ax.plot([x1, x2], [y1, y2], color="#c7d2fe", linewidth=0.8, zorder=1)
    for node, (x, y) in positions.items():
        color = "#ffffff"
        edge = "#64748b"
        if node == level.start_node:
            color = "#dcfce7"
            edge = "#16a34a"
        elif node == level.goal_node:
            color = "#fee2e2"
            edge = "#dc2626"
        elif node in level.mines:
            color = "#fef3c7"
            edge = "#d97706"
        elif node in level.villages:
            color = "#e0f2fe"
            edge = "#0284c7"
        ax.scatter([x], [y], s=190 if level_id == 2 else 240, c=color, edgecolors=edge, linewidths=1.2, zorder=3)
        ax.text(x, y, str(node), ha="center", va="center", fontsize=7 if level_id == 2 else 9, zorder=4)
    route_xy = [positions[node] for node in route if node in positions]
    if route_xy:
        ax.plot([p[0] for p in route_xy], [p[1] for p in route_xy], color="#ef4444", linewidth=2.4, zorder=5)
        ax.scatter([p[0] for p in route_xy], [p[1] for p in route_xy], color="#ef4444", s=24, zorder=6)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    ax.set_title("Level %s route on auto-extracted map" % level_id)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _file_info(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _safe_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> Optional[int]:
    number = _safe_float(value)
    return int(number) if number is not None else None


def _split_weather_sequence(value: str) -> List[str]:
    tokens: List[str] = []
    rest = value.strip()
    names = ("晴朗", "高温", "沙暴")
    while rest:
        matched = False
        for name in names:
            if rest.startswith(name):
                tokens.append(name)
                rest = rest[len(name):]
                matched = True
                break
        if not matched:
            rest = rest[1:]
    return tokens


def _read_scenario_table(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            weather_tokens = _split_weather_sequence(raw.get("weather", ""))
            rows.append(
                {
                    "scenario": _safe_int(raw.get("scenario")),
                    "weather": raw.get("weather", ""),
                    "weather_tokens": weather_tokens,
                    "storm_count": weather_tokens.count("沙暴"),
                    "hot_count": weather_tokens.count("高温"),
                    "sunny_count": weather_tokens.count("晴朗"),
                    "feasible": raw.get("feasible") == "True",
                    "objective": _safe_float(raw.get("objective")),
                    "arrival_day": _safe_int(raw.get("arrival_day")),
                    "status": raw.get("status", ""),
                    "message": raw.get("message", ""),
                }
            )
    return rows


def _load_json(path: Path, fallback: object) -> object:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _trace_stats(trace: Mapping[str, object]) -> Dict[str, object]:
    rows = _rows(trace)
    if not rows:
        return {}
    action_counts: Dict[str, int] = {}
    weather_counts: Dict[str, int] = {}
    route_edges = 0
    for row in rows:
        action = str(row.get("action") or "unknown")
        weather = str(row.get("weather") or "none")
        action_counts[action] = action_counts.get(action, 0) + 1
        weather_counts[weather] = weather_counts.get(weather, 0) + 1
        if row.get("from_node") != row.get("to_node"):
            route_edges += 1
    final = rows[-1]
    total_income = sum(float(row.get("income") or 0) for row in rows)
    total_water = sum(float(row.get("consume_water") or 0) for row in rows)
    total_food = sum(float(row.get("consume_food") or 0) for row in rows)
    return {
        "arrival_day": final.get("day"),
        "final_node": final.get("node"),
        "final_cash": final.get("cash"),
        "final_water": final.get("water"),
        "final_food": final.get("food"),
        "unique_nodes": len({row.get("node") for row in rows}),
        "route_edges": route_edges,
        "mine_days": action_counts.get("mine", 0),
        "village_purchases": sum(1 for row in rows if row.get("note") == "village purchase"),
        "total_income": total_income,
        "total_water_consumed": total_water,
        "total_food_consumed": total_food,
        "min_water": min(float(row.get("water") or 0) for row in rows),
        "min_food": min(float(row.get("food") or 0) for row in rows),
        "action_counts": action_counts,
        "weather_counts": weather_counts,
    }


def _frontend_level_payload(level_id: int) -> Dict[str, object]:
    levels = load_level_map()
    level = levels[level_id]
    positions = LEVEL1_POSITIONS if level_id == 1 else level2_positions()
    return {
        "level_id": level.level_id,
        "name": level.name,
        "deadline": level.deadline,
        "carry_limit_kg": level.carry_limit_kg,
        "initial_cash": level.initial_cash,
        "base_income": level.base_income,
        "start_node": level.start_node,
        "goal_node": level.goal_node,
        "mines": list(level.mines),
        "villages": list(level.villages),
        "weather": list(level.weather) if level.weather else None,
        "weather_policy": dict(level.weather_policy),
        "adjacency": {str(node): list(nbrs) for node, nbrs in level.adjacency.items()},
        "positions": {str(node): {"x": x, "y": y} for node, (x, y) in positions.items()},
        "players": level.players,
        "notes": list(level.notes),
    }


def _build_frontend_payload(traces: Mapping[int, Mapping[str, object]], output_root: Path) -> Dict[str, object]:
    report_tables = output_root / "report_tables"
    scenario_tables = {
        "3": _read_scenario_table(report_tables / "level_3_scenarios.csv"),
        "4": _read_scenario_table(report_tables / "level_4_scenarios.csv"),
    }
    analysis_summary = _load_json(report_tables / "analysis_summary.json", [])
    levels = {str(level_id): _frontend_level_payload(level_id) for level_id in range(1, 7)}
    sources = {
        "level_1_trace": _file_info(output_root / "solutions" / "level_1_trace.json"),
        "level_2_trace": _file_info(output_root / "solutions" / "level_2_trace.json"),
        "analysis_summary": _file_info(report_tables / "analysis_summary.json"),
        "algorithm_benchmark": _file_info(output_root / "experiments" / "algorithm_benchmark.json"),
        "algorithm_comparison": _file_info(report_tables / "algorithm_comparison.md"),
        "core_solver_optimization": _file_info(output_root / "logs" / "core_solver_optimization.md"),
        "level_3_scenarios": _file_info(report_tables / "level_3_scenarios.csv"),
        "level_4_scenarios": _file_info(report_tables / "level_4_scenarios.csv"),
        "config": _file_info(Path(__file__).resolve().parents[1] / "configs" / "levels.json"),
        "problem_summary": _file_info(output_root / "extracted" / "problem_summary.json"),
        "attachment_summary": _file_info(output_root / "extracted" / "attachment_summary.json"),
        "problem_vml_summary": _file_info(output_root / "extracted" / "problem_vml_summary.json"),
        "attachment_vml_summary": _file_info(output_root / "extracted" / "attachment_vml_summary.json"),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "traces": {
            str(level_id): {
                **dict(trace),
                "stats": _trace_stats(trace),
            }
            for level_id, trace in traces.items()
        },
        "levels": levels,
        "analysis_summary": analysis_summary,
        "scenario_tables": scenario_tables,
        "extracted_problem": _load_json(output_root / "extracted" / "problem_summary.json", {}),
        "extracted_attachment": _load_json(output_root / "extracted" / "attachment_summary.json", {}),
        "vml_summaries": {
            "problem": _load_json(output_root / "extracted" / "problem_vml_summary.json", {}),
            "attachment": _load_json(output_root / "extracted" / "attachment_vml_summary.json", {}),
        },
        "sources": sources,
        "figure_paths": {
            "level_1_path": "../figures/level_1_path.png",
            "level_1_resources": "../figures/level_1_resources.png",
            "level_2_path": "../figures/level_2_path.png",
            "level_2_resources": "../figures/level_2_resources.png",
        },
    }


def write_frontend(traces: Mapping[int, Mapping[str, object]], output_root: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "dashboard-data.js"
    payload = _build_frontend_payload(traces, output_root)
    data_path.write_text(
        "window.DESERT_DASHBOARD_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    template_dir = Path(__file__).resolve().parent / "frontend_templates"
    template_names = [
        "index.html",
        "styles.css",
        "data-adapter.js",
        "interaction-state.js",
        "charts.js",
        "app.js",
    ]
    for name in template_names:
        source = template_dir / name
        if not source.exists():
            raise FileNotFoundError("frontend template missing: %s" % source)
        (output_dir / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return output_dir / "index.html"
    html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Desert Crossing Policy Visual Analytics</title>
  <style>
    :root {
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #64748b;
      --line: #dbe1ea;
      --soft: #edf2f7;
      --blue: #2f6fbd;
      --blue-soft: #dbeafe;
      --gold: #b7791f;
      --gold-soft: #fef3c7;
      --green: #2f855a;
      --green-soft: #dcfce7;
      --red: #c2410c;
      --red-soft: #ffedd5;
      --pink: #a43f68;
      --shadow: 0 1px 2px rgba(15, 23, 42, .05);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      letter-spacing: 0;
    }
    h2, h3 { margin: 0; font-size: 14px; line-height: 1.3; }
    button, input { font: inherit; }
    main { padding: 8px 12px 14px; }
    .kpi-strip {
      display: grid;
      grid-template-columns: repeat(6, minmax(128px, 1fr));
      gap: 7px;
      margin-bottom: 8px;
    }
    .kpi-card, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .kpi-card { padding: 7px 9px; min-height: 54px; }
    .kpi-label { color: var(--muted); font-size: 10px; line-height: 1.18; }
    .kpi-value { margin-top: 3px; font-size: 18px; line-height: 1; font-weight: 760; }
    .kpi-note { margin-top: 4px; color: var(--muted); font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .dashboard-grid {
      display: grid;
      grid-template-columns: minmax(320px, .94fr) minmax(420px, 1.42fr) minmax(300px, .9fr);
      gap: 8px;
      align-items: start;
    }
    .panel { min-width: 0; overflow: hidden; }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 7px 10px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .panel-body { padding: 9px; }
    .control-row { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
    .segmented, .tab-list { display: flex; flex-wrap: wrap; gap: 5px; }
    .segmented button, .tab-list button, .view-switch button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      min-height: 28px;
      border-radius: 7px;
      padding: 4px 8px;
      cursor: pointer;
    }
    .segmented button.active, .tab-list button.active, .view-switch button.active {
      border-color: #8eb6e8;
      background: var(--blue-soft);
      color: #17477d;
      font-weight: 700;
    }
    .view-switch {
      display: grid;
      grid-template-columns: repeat(5, minmax(92px, 1fr));
      gap: 5px;
      margin-bottom: 7px;
    }
    .view-switch button { width: 100%; padding: 5px 6px; font-size: 11px; white-space: normal; }
    .route-shell {
      display: grid;
      grid-template-rows: auto auto;
      gap: 7px;
    }
    .svg-wrap {
      width: 100%;
      min-height: 260px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    svg { display: block; width: 100%; }
    #routeSvg { height: 286px; }
    #temporalSvg { height: 302px; }
    #diagnosticSvg { height: 188px; }
    .timeline-control {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 7px;
      align-items: center;
    }
    .timeline-control input { width: 100%; accent-color: var(--blue); }
    .badge-row { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 6px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      background: #fff;
      font-size: 11px;
      line-height: 1.2;
    }
    .badge.blue { color: #17477d; background: var(--blue-soft); border-color: #bfdbfe; }
    .badge.gold { color: #7c4a03; background: var(--gold-soft); border-color: #fde68a; }
    .badge.green { color: #166534; background: var(--green-soft); border-color: #bbf7d0; }
    .badge.red { color: #9a3412; background: var(--red-soft); border-color: #fed7aa; }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }
    .detail-cell { padding: 7px 8px; border-bottom: 1px solid var(--line); }
    .detail-cell:nth-child(odd) { border-right: 1px solid var(--line); }
    .detail-cell:nth-last-child(-n + 2) { border-bottom: 0; }
    .detail-label { color: var(--muted); font-size: 11px; }
    .detail-value { margin-top: 3px; font-weight: 700; font-size: 13px; }
    .source-list, .diagnostic-list { margin: 0; padding: 0; list-style: none; }
    .source-list li, .diagnostic-list li {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      padding: 6px 0;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }
    .source-list li:last-child, .diagnostic-list li:last-child { border-bottom: 0; }
    .table-scroll { max-height: 220px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th, td { padding: 7px 8px; border-bottom: 1px solid #e8edf5; text-align: left; font-size: 12px; white-space: nowrap; }
    th { position: sticky; top: 0; z-index: 1; background: #f8fafc; color: #475569; font-weight: 700; }
    tr.selected { background: #eaf3ff; }
    .axis text { fill: #64748b; font-size: 11px; }
    .axis path, .axis line { stroke: #cbd5e1; }
    .grid-line { stroke: #edf2f7; stroke-width: 1; }
    .tooltip {
      position: fixed;
      pointer-events: none;
      z-index: 10;
      max-width: 260px;
      padding: 8px 9px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: rgba(255,255,255,.96);
      box-shadow: 0 8px 24px rgba(15,23,42,.12);
      color: var(--ink);
      font-size: 12px;
      line-height: 1.45;
      opacity: 0;
    }
    @media (max-width: 1180px) {
      .dashboard-grid { grid-template-columns: 1fr; }
      #routeSvg, #temporalSvg { height: 315px; }
    }
    @media (max-width: 760px) {
      main { padding: 8px; }
      .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .view-switch { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .timeline-control { grid-template-columns: 1fr; }
      .detail-grid { grid-template-columns: 1fr; }
      .detail-cell:nth-child(odd) { border-right: 0; }
      .detail-cell:nth-last-child(-n + 2) { border-bottom: 1px solid var(--line); }
      .detail-cell:last-child { border-bottom: 0; }
    }
  </style>
</head>
<body>
  <main>
    <section class="kpi-strip" id="summaryCards"></section>
    <section class="dashboard-grid">
      <section class="panel">
        <div class="panel-header">
          <h2>Route Replay</h2>
          <div class="segmented" id="levelTabs"></div>
        </div>
        <div class="panel-body route-shell">
          <div class="svg-wrap"><svg id="routeSvg" role="img" aria-label="route replay map"></svg></div>
          <div class="timeline-control">
            <span class="badge blue" id="dayBadge">Day --</span>
            <input id="daySlider" type="range" min="0" value="0" step="1">
            <span class="badge" id="nodeBadge">Node --</span>
          </div>
          <div class="detail-grid" id="frameDetails"></div>
          <div class="badge-row" id="routeBadges"></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Temporal Analytics</h2>
          <span class="badge" id="temporalSubtitle">speedChart</span>
        </div>
        <div class="panel-body">
          <div class="view-switch" id="temporalButtons"></div>
          <div class="svg-wrap"><svg id="temporalSvg" role="img" aria-label="temporal analytics"></svg></div>
          <div class="badge-row" id="temporalLegend"></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Diagnostics / Details</h2>
          <div class="tab-list" id="diagnosticTabs"></div>
        </div>
        <div class="panel-body">
          <div id="diagnosticContent"></div>
          <div class="svg-wrap" id="diagnosticChartWrap"><svg id="diagnosticSvg" role="img" aria-label="diagnostic chart"></svg></div>
        </div>
      </section>
    </section>
  </main>
  <div class="tooltip" id="tooltip"></div>
  <script src="vendor/d3.v7.min.js"></script>
  <script src="dashboard-data.js"></script>
  <script>
    const DATA = window.DESERT_DASHBOARD_DATA;
    const state = { levelId: "1", day: 0, temporalView: "speedChart", diagnosticTab: "details" };
    const colors = {
      water: "#2f6fbd",
      food: "#2f855a",
      cash: "#b7791f",
      route: "#c2410c",
      storm: "#a43f68",
      hot: "#b7791f",
      sunny: "#2f855a",
      move: "#2f6fbd",
      stay: "#64748b",
      mine: "#b7791f",
      buy_start: "#2f855a"
    };
    const temporalViews = [
      ["speedChart", "speedChart"],
      ["spatialValidity", "spatialValidity"],
      ["sourceStack", "sourceStack"],
      ["allVideoTimeline", "allVideoTimeline"],
      ["workloadPanel", "workloadPanel"]
    ];
    const diagnosticTabs = [
      ["details", "Details"],
      ["scenarios", "Scenarios"],
      ["diagnostics", "Diagnostics"]
    ];
    const tooltip = d3.select("#tooltip");

    function trace() { return DATA.traces[state.levelId]; }
    function level() { return DATA.levels[state.levelId]; }
    function rows() { return trace().rows || []; }
    function selectedRow() { return rows()[state.day] || rows()[0] || {}; }
    function fmt(value, digits = 0) {
      if (value === null || value === undefined || value === "") return "--";
      if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: digits });
      const number = Number(value);
      return Number.isFinite(number) ? number.toLocaleString("en-US", { maximumFractionDigits: digits }) : value;
    }
    function showTip(event, html) {
      tooltip.html(html).style("left", `${event.clientX + 12}px`).style("top", `${event.clientY + 12}px`).style("opacity", 1);
    }
    function hideTip() { tooltip.style("opacity", 0); }
    function clearSvg(selector) { d3.select(selector).selectAll("*").remove(); }
    function svgBox(selector) {
      const node = document.querySelector(selector);
      const width = Math.max(320, node.clientWidth || 640);
      const height = Math.max(220, node.clientHeight || 320);
      return { width, height };
    }

    function renderSummary() {
      const summaries = DATA.analysis_summary || [];
      const l1 = DATA.traces["1"].stats || {};
      const l2 = DATA.traces["2"].stats || {};
      const robust = summaries.filter(d => d.scenario_count).reduce((acc, d) => acc + (d.feasible_scenarios || 0), 0);
      const total = summaries.filter(d => d.scenario_count).reduce((acc, d) => acc + (d.scenario_count || 0), 0);
      const cards = [
        ["L1 Objective", fmt(DATA.traces["1"].objective_value, 1), `arrival day ${fmt(l1.arrival_day)}`],
        ["L2 Objective", fmt(DATA.traces["2"].objective_value, 1), `arrival day ${fmt(l2.arrival_day)}`],
        ["Scenario Coverage", `${robust}/${total}`, "levels 3-4 feasible"],
        ["L1 Mining Days", fmt(l1.mine_days), `${fmt(l1.total_income)} income`],
        ["L2 Mining Days", fmt(l2.mine_days), `${fmt(l2.total_income)} income`],
        ["Co-op Risk", "blocked", "levels 5-6 cooperative checks"]
      ];
      d3.select("#summaryCards").selectAll(".kpi-card")
        .data(cards)
        .join("article")
        .attr("class", "kpi-card")
        .html(d => `<div class="kpi-label">${d[0]}</div><div class="kpi-value">${d[1]}</div><div class="kpi-note">${d[2]}</div>`);
    }

    function renderControls() {
      d3.select("#levelTabs").selectAll("button")
        .data(["1", "2"])
        .join("button")
        .attr("class", d => d === state.levelId ? "active" : null)
        .text(d => `Level ${d}`)
        .on("click", (_, d) => {
          state.levelId = d;
          state.day = Math.min(state.day, rows().length - 1);
          renderAll();
        });
      d3.select("#temporalButtons").selectAll("button")
        .data(temporalViews)
        .join("button")
        .attr("class", d => d[0] === state.temporalView ? "active" : null)
        .text(d => d[1])
        .on("click", (_, d) => {
          state.temporalView = d[0];
          renderTemporal();
        });
      d3.select("#diagnosticTabs").selectAll("button")
        .data(diagnosticTabs)
        .join("button")
        .attr("class", d => d[0] === state.diagnosticTab ? "active" : null)
        .text(d => d[1])
        .on("click", (_, d) => {
          state.diagnosticTab = d[0];
          renderDiagnostics();
        });
      const slider = d3.select("#daySlider")
        .attr("max", Math.max(0, rows().length - 1))
        .property("value", state.day)
        .on("input", event => {
          state.day = Number(event.target.value);
          renderRoute();
          renderDiagnostics();
        });
      slider.property("value", state.day);
    }

    function renderRoute() {
      const allRows = rows();
      const current = selectedRow();
      const meta = level();
      d3.select("#dayBadge").text(`Day ${fmt(current.day)}`);
      d3.select("#nodeBadge").text(`Node ${fmt(current.node)}`);
      d3.select("#daySlider").attr("max", Math.max(0, allRows.length - 1)).property("value", state.day);
      const details = [
        ["Action", current.action || "--"],
        ["Weather", current.weather || "--"],
        ["Cash", fmt(current.cash)],
        ["Resource", `W ${fmt(current.water)} / F ${fmt(current.food)}`],
        ["Consumption", `W ${fmt(current.consume_water)} / F ${fmt(current.consume_food)}`],
        ["Income", fmt(current.income)]
      ];
      d3.select("#frameDetails").selectAll(".detail-cell")
        .data(details)
        .join("div")
        .attr("class", "detail-cell")
        .html(d => `<div class="detail-label">${d[0]}</div><div class="detail-value">${d[1]}</div>`);
      const badges = [
        ["blue", `start ${meta.start_node}`],
        ["red", `goal ${meta.goal_node}`],
        ["gold", `mines ${meta.mines.join(", ") || "--"}`],
        ["green", `villages ${meta.villages.join(", ") || "--"}`]
      ];
      d3.select("#routeBadges").selectAll(".badge")
        .data(badges)
        .join("span")
        .attr("class", d => `badge ${d[0]}`)
        .text(d => d[1]);

      clearSvg("#routeSvg");
      const { width, height } = svgBox("#routeSvg");
      const svg = d3.select("#routeSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const isDenseMap = meta.level_id === 2;
      const pad = isDenseMap ? 18 : 24;
      const routeStroke = isDenseMap ? 2.1 : 2.8;
      const nodeRadius = d => {
        const keyNode = d.node === meta.start_node || d.node === meta.goal_node;
        return isDenseMap ? (keyNode ? 6.2 : 4.3) : (keyNode ? 8 : 5.6);
      };
      const labelSize = isDenseMap ? 6.8 : 9.2;
      const currentRing = isDenseMap ? 10 : 13;
      const positions = Object.entries(meta.positions).map(([node, p]) => ({ node: Number(node), x: p.x, y: p.y }));
      const x = d3.scaleLinear().domain(d3.extent(positions, d => d.x)).range([pad, width - pad]);
      const y = d3.scaleLinear().domain(d3.extent(positions, d => d.y)).range([height - pad, pad]);
      const edges = [];
      Object.entries(meta.adjacency).forEach(([node, ns]) => {
        ns.forEach(n => { if (Number(n) > Number(node)) edges.push({ source: Number(node), target: Number(n) }); });
      });
      const pos = new Map(positions.map(d => [d.node, d]));
      svg.append("g").selectAll("line")
        .data(edges)
        .join("line")
        .attr("x1", d => x(pos.get(d.source).x))
        .attr("y1", d => y(pos.get(d.source).y))
        .attr("x2", d => x(pos.get(d.target).x))
        .attr("y2", d => y(pos.get(d.target).y))
        .attr("stroke", "#d9e2ef")
        .attr("stroke-width", 1);
      const routeNodes = allRows.slice(0, state.day + 1).map(d => Number(d.node)).filter(n => pos.has(n));
      const routeLine = d3.line().x(n => x(pos.get(n).x)).y(n => y(pos.get(n).y)).curve(d3.curveLinear);
      if (routeNodes.length > 1) {
        svg.append("path")
          .attr("d", routeLine(routeNodes))
          .attr("fill", "none")
          .attr("stroke", colors.route)
          .attr("stroke-width", routeStroke)
          .attr("stroke-linejoin", "round")
          .attr("stroke-linecap", "round");
      }
      svg.append("g").selectAll("circle")
        .data(positions)
        .join("circle")
        .attr("cx", d => x(d.x))
        .attr("cy", d => y(d.y))
        .attr("r", d => nodeRadius(d))
        .attr("fill", d => meta.start_node === d.node ? "#dcfce7" : meta.goal_node === d.node ? "#ffedd5" : meta.mines.includes(d.node) ? "#fef3c7" : meta.villages.includes(d.node) ? "#dbeafe" : "#fff")
        .attr("stroke", d => Number(current.node) === d.node ? colors.route : "#64748b")
        .attr("stroke-width", d => Number(current.node) === d.node ? 2.8 : 1.1)
        .on("mousemove", (event, d) => showTip(event, `Node ${d.node}`))
        .on("mouseleave", hideTip);
      svg.append("g").selectAll("text")
        .data(positions)
        .join("text")
        .attr("x", d => x(d.x))
        .attr("y", d => y(d.y) + (isDenseMap ? 2.4 : 3))
        .attr("text-anchor", "middle")
        .attr("font-size", labelSize)
        .attr("fill", "#172033")
        .text(d => d.node);
      if (pos.has(Number(current.node))) {
        const p = pos.get(Number(current.node));
        svg.append("circle")
          .attr("cx", x(p.x))
          .attr("cy", y(p.y))
          .attr("r", currentRing)
          .attr("fill", "none")
          .attr("stroke", colors.route)
          .attr("stroke-width", 2)
          .attr("stroke-dasharray", "4 3");
      }
    }

    function addAxes(svg, xScale, yScale, width, height, margin) {
      svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - margin.bottom})`).call(d3.axisBottom(xScale).ticks(6).tickSizeOuter(0));
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(yScale).ticks(5).tickSizeOuter(0));
      svg.append("g").selectAll("line")
        .data(yScale.ticks(5))
        .join("line")
        .attr("class", "grid-line")
        .attr("x1", margin.left)
        .attr("x2", width - margin.right)
        .attr("y1", d => yScale(d))
        .attr("y2", d => yScale(d));
    }

    function renderSpeedChart() {
      clearSvg("#temporalSvg");
      const { width, height } = svgBox("#temporalSvg");
      const margin = { top: 26, right: 22, bottom: 34, left: 44 };
      const svg = d3.select("#temporalSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const data = rows().map(d => ({ day: +d.day, water: +d.water, food: +d.food, cash: +d.cash }));
      const x = d3.scaleLinear().domain(d3.extent(data, d => d.day)).range([margin.left, width - margin.right]);
      const maxResource = d3.max(data, d => Math.max(d.water, d.food, d.cash / 25)) || 1;
      const y = d3.scaleLinear().domain([0, maxResource]).nice().range([height - margin.bottom, margin.top]);
      addAxes(svg, x, y, width, height, margin);
      const series = [
        ["water", data.map(d => ({ day: d.day, value: d.water }))],
        ["food", data.map(d => ({ day: d.day, value: d.food }))],
        ["cash", data.map(d => ({ day: d.day, value: d.cash / 25 }))]
      ];
      const line = d3.line().x(d => x(d.day)).y(d => y(d.value)).curve(d3.curveMonotoneX);
      svg.append("g").selectAll("path")
        .data(series)
        .join("path")
        .attr("fill", "none")
        .attr("stroke", d => colors[d[0]])
        .attr("stroke-width", 2.4)
        .attr("d", d => line(d[1]));
      svg.append("line")
        .attr("x1", x(selectedRow().day)).attr("x2", x(selectedRow().day))
        .attr("y1", margin.top).attr("y2", height - margin.bottom)
        .attr("stroke", colors.route).attr("stroke-width", 1.6).attr("stroke-dasharray", "4 4");
      svg.append("text").attr("x", margin.left).attr("y", 16).attr("font-size", 12).attr("font-weight", 700).text("Resource trajectory (cash /25)");
      renderLegend([["water", "water boxes"], ["food", "food boxes"], ["cash", "cash / 25"]]);
    }

    function renderSpatialValidity() {
      clearSvg("#temporalSvg");
      const { width, height } = svgBox("#temporalSvg");
      const svg = d3.select("#temporalSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const meta = level();
      const graph = meta.adjacency;
      const data = rows().slice(1).map(d => {
        const from = String(d.from_node);
        const to = Number(d.to_node);
        const valid = from === String(to) || (graph[from] || []).includes(to);
        return { day: +d.day, from: +d.from_node, to, action: d.action, valid };
      });
      const counts = [
        { label: "valid route edges", value: data.filter(d => d.valid).length, color: colors.green },
        { label: "self/stay/mine frames", value: data.filter(d => d.from === d.to).length, color: "#64748b" },
        { label: "invalid transitions", value: data.filter(d => !d.valid).length, color: colors.route }
      ];
      const margin = { top: 32, right: 24, bottom: 42, left: 132 };
      const x = d3.scaleLinear().domain([0, d3.max(counts, d => d.value) || 1]).range([margin.left, width - margin.right]);
      const y = d3.scaleBand().domain(counts.map(d => d.label)).range([margin.top, height - margin.bottom]).padding(.28);
      svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - margin.bottom})`).call(d3.axisBottom(x).ticks(5).tickSizeOuter(0));
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y).tickSizeOuter(0));
      svg.append("g").selectAll("rect")
        .data(counts)
        .join("rect")
        .attr("x", margin.left)
        .attr("y", d => y(d.label))
        .attr("width", d => x(d.value) - margin.left)
        .attr("height", y.bandwidth())
        .attr("fill", d => d.color)
        .attr("opacity", .88);
      svg.append("g").selectAll("text.value")
        .data(counts)
        .join("text")
        .attr("x", d => x(d.value) + 6)
        .attr("y", d => y(d.label) + y.bandwidth() / 2 + 4)
        .attr("font-size", 12)
        .attr("fill", "#475569")
        .text(d => d.value);
      svg.append("text").attr("x", margin.left).attr("y", 18).attr("font-size", 12).attr("font-weight", 700).text("Route transition validity");
      renderLegend([["green", "valid"], ["stay", "self frame"], ["route", "invalid"]]);
    }

    function renderSourceStack() {
      clearSvg("#temporalSvg");
      const { width, height } = svgBox("#temporalSvg");
      const svg = d3.select("#temporalSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const actions = Array.from(new Set(rows().map(d => d.action)));
      const weathers = ["晴朗", "高温", "沙暴", "none"];
      const data = actions.map(action => {
        const row = { action };
        weathers.forEach(w => row[w] = rows().filter(d => d.action === action && (d.weather || "none") === w).length);
        return row;
      });
      const stack = d3.stack().keys(weathers)(data);
      const margin = { top: 30, right: 20, bottom: 42, left: 48 };
      const x = d3.scaleBand().domain(actions).range([margin.left, width - margin.right]).padding(.24);
      const y = d3.scaleLinear().domain([0, d3.max(data, d => weathers.reduce((s, w) => s + d[w], 0)) || 1]).nice().range([height - margin.bottom, margin.top]);
      const c = d3.scaleOrdinal().domain(weathers).range([colors.sunny, colors.hot, colors.storm, "#94a3b8"]);
      addAxes(svg, x, y, width, height, margin);
      svg.append("g").selectAll("g")
        .data(stack)
        .join("g")
        .attr("fill", d => c(d.key))
        .selectAll("rect")
        .data(d => d)
        .join("rect")
        .attr("x", d => x(d.data.action))
        .attr("y", d => y(d[1]))
        .attr("height", d => y(d[0]) - y(d[1]))
        .attr("width", x.bandwidth());
      svg.append("text").attr("x", margin.left).attr("y", 18).attr("font-size", 12).attr("font-weight", 700).text("Action by weather");
      renderLegend([["sunny", "晴朗"], ["hot", "高温"], ["storm", "沙暴"], ["stay", "initial"]]);
    }

    function renderAllVideoTimeline() {
      clearSvg("#temporalSvg");
      const { width, height } = svgBox("#temporalSvg");
      const svg = d3.select("#temporalSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const lanes = [
        { label: "L1 route", rows: DATA.traces["1"].rows },
        { label: "L2 route", rows: DATA.traces["2"].rows }
      ];
      const margin = { top: 30, right: 22, bottom: 30, left: 82 };
      const x = d3.scaleLinear().domain([0, 30]).range([margin.left, width - margin.right]);
      const y = d3.scaleBand().domain(lanes.map(d => d.label)).range([margin.top, 128]).padding(.35);
      svg.append("g").attr("class", "axis").attr("transform", `translate(0,${128})`).call(d3.axisBottom(x).ticks(10).tickSizeOuter(0));
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y).tickSizeOuter(0));
      lanes.forEach(lane => {
        svg.append("g").selectAll("rect")
          .data(lane.rows)
          .join("rect")
          .attr("x", d => x(d.day) - 3)
          .attr("y", y(lane.label))
          .attr("width", 6)
          .attr("height", y.bandwidth())
          .attr("rx", 2)
          .attr("fill", d => colors[d.action] || "#94a3b8")
          .on("mousemove", (event, d) => showTip(event, `${lane.label}<br>Day ${d.day}, node ${d.node}<br>${d.action} / ${d.weather || "--"}`))
          .on("mouseleave", hideTip);
      });
      const scenarioSummary = Object.entries(DATA.scenario_tables).map(([levelId, table]) => ({
        levelId,
        feasible: table.filter(d => d.feasible).length,
        total: table.length,
        arrival: d3.mean(table, d => d.arrival_day)
      }));
      const y2 = d3.scaleBand().domain(scenarioSummary.map(d => `L${d.levelId} scenarios`)).range([178, height - margin.bottom]).padding(.32);
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y2).tickSizeOuter(0));
      scenarioSummary.forEach(d => {
        svg.append("rect")
          .attr("x", margin.left)
          .attr("y", y2(`L${d.levelId} scenarios`))
          .attr("width", (width - margin.right - margin.left) * (d.feasible / Math.max(1, d.total)))
          .attr("height", y2.bandwidth())
          .attr("fill", colors.green)
          .attr("opacity", .82);
        svg.append("text")
          .attr("x", margin.left + 8)
          .attr("y", y2(`L${d.levelId} scenarios`) + y2.bandwidth() / 2 + 4)
          .attr("font-size", 12)
          .attr("fill", "#172033")
          .text(`${d.feasible}/${d.total} feasible, avg arrival day ${fmt(d.arrival, 1)}`);
      });
      svg.append("text").attr("x", margin.left).attr("y", 18).attr("font-size", 12).attr("font-weight", 700).text("Route and scenario timeline");
      renderLegend([["move", "move"], ["stay", "stay"], ["cash", "mine"], ["green", "feasible scenarios"]]);
    }

    function renderWorkloadPanel() {
      clearSvg("#temporalSvg");
      const { width, height } = svgBox("#temporalSvg");
      const svg = d3.select("#temporalSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const summaries = (DATA.analysis_summary || []).filter(d => d.multiplayer);
      const rows = summaries.flatMap(d => (d.multiplayer.effect_table || []).map(e => ({
        level: `L${d.level_id}`,
        k: e.same_group_count,
        move: e.move_multiplier,
        income: e.income_multiplier,
        village: e.village_price_multiplier,
        feasible: d.cooperative_analysis && (d.cooperative_analysis.feasible === false || d.cooperative_analysis.failure_rate === 1) ? "blocked" : "ok"
      })));
      const margin = { top: 32, right: 24, bottom: 42, left: 64 };
      const x = d3.scaleBand().domain(rows.map(d => `${d.level} k=${d.k}`)).range([margin.left, width - margin.right]).padding(.26);
      const y = d3.scaleLinear().domain([0, d3.max(rows, d => d.move) || 1]).nice().range([height - margin.bottom, margin.top]);
      addAxes(svg, x, y, width, height, margin);
      svg.append("g").selectAll("rect")
        .data(rows)
        .join("rect")
        .attr("x", d => x(`${d.level} k=${d.k}`))
        .attr("y", d => y(d.move))
        .attr("width", x.bandwidth())
        .attr("height", d => y(0) - y(d.move))
        .attr("fill", d => d.feasible === "blocked" ? colors.route : colors.blue)
        .attr("opacity", .86)
        .on("mousemove", (event, d) => showTip(event, `${d.level}, k=${d.k}<br>move multiplier ${d.move}<br>income multiplier ${fmt(d.income, 2)}`))
        .on("mouseleave", hideTip);
      svg.append("text").attr("x", margin.left).attr("y", 18).attr("font-size", 12).attr("font-weight", 700).text("Cooperative workload");
      renderLegend([["route", "blocked cooperation"], ["blue", "multiplier"]]);
    }

    function renderLegend(items) {
      d3.select("#temporalLegend").selectAll(".badge")
        .data(items)
        .join("span")
        .attr("class", d => `badge ${d[0]}`)
        .text(d => d[1]);
    }

    function renderTemporal() {
      d3.select("#temporalSubtitle").text(state.temporalView);
      renderControls();
      if (state.temporalView === "speedChart") renderSpeedChart();
      if (state.temporalView === "spatialValidity") renderSpatialValidity();
      if (state.temporalView === "sourceStack") renderSourceStack();
      if (state.temporalView === "allVideoTimeline") renderAllVideoTimeline();
      if (state.temporalView === "workloadPanel") renderWorkloadPanel();
    }

    function renderDiagnostics() {
      clearSvg("#diagnosticSvg");
      d3.select("#diagnosticChartWrap").style("display", "block");
      const content = d3.select("#diagnosticContent");
      const current = selectedRow();
      if (state.diagnosticTab === "details") {
        content.html(`
          <div class="detail-grid">
            <div class="detail-cell"><div class="detail-label">Selected frame</div><div class="detail-value">L${state.levelId} / day ${fmt(current.day)}</div></div>
            <div class="detail-cell"><div class="detail-label">Node transition</div><div class="detail-value">${fmt(current.from_node)} -> ${fmt(current.to_node)}</div></div>
            <div class="detail-cell"><div class="detail-label">Water/Food purchase</div><div class="detail-value">${fmt(current.buy_water)} / ${fmt(current.buy_food)}</div></div>
            <div class="detail-cell"><div class="detail-label">Note</div><div class="detail-value">${current.note || "--"}</div></div>
          </div>
          <div class="table-scroll" style="margin-top:10px">
            <table><thead><tr><th>Day</th><th>Node</th><th>Action</th><th>Weather</th><th>Cash</th><th>Water</th><th>Food</th></tr></thead><tbody>
              ${rows().map((r, i) => `<tr class="${i === state.day ? "selected" : ""}" data-day="${i}"><td>${r.day}</td><td>${r.node}</td><td>${r.action}</td><td>${r.weather || ""}</td><td>${r.cash}</td><td>${r.water}</td><td>${r.food}</td></tr>`).join("")}
            </tbody></table>
          </div>
        `);
        content.selectAll("tbody tr").on("click", function() {
          state.day = Number(this.dataset.day);
          renderRoute();
          renderDiagnostics();
          renderTemporal();
        });
        renderMiniResourceBars();
      } else if (state.diagnosticTab === "scenarios") {
        const summaryHtml = Object.entries(DATA.scenario_tables).map(([levelId, table]) => {
          const feasible = table.filter(d => d.feasible).length;
          const arrivals = table.map(d => d.arrival_day).filter(Boolean);
          return `<li><span>Level ${levelId} scenarios</span><strong>${feasible}/${table.length} feasible, arrival ${fmt(d3.mean(arrivals), 1)}</strong></li>`;
        }).join("");
        content.html(`<ul class="diagnostic-list">${summaryHtml}</ul>`);
        renderScenarioHeatmap();
      } else {
        const sourceHtml = Object.entries(DATA.sources).map(([name, source]) => {
          const status = source.exists ? source.modified : "missing";
          return `<li><span>${name}</span><strong>${status}</strong></li>`;
        }).join("");
        const notes = (level().notes || []).map(note => `<li><span>${note}</span><strong>note</strong></li>`).join("");
        content.html(`<ul class="source-list">${sourceHtml}</ul><ul class="diagnostic-list" style="margin-top:8px">${notes}</ul>`);
        renderSourceFreshness();
      }
    }

    function renderMiniResourceBars() {
      const { width, height } = svgBox("#diagnosticSvg");
      const svg = d3.select("#diagnosticSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const current = selectedRow();
      const data = [
        { label: "water", value: +current.water, max: d3.max(rows(), d => +d.water) || 1, color: colors.water },
        { label: "food", value: +current.food, max: d3.max(rows(), d => +d.food) || 1, color: colors.food },
        { label: "cash", value: +current.cash, max: d3.max(rows(), d => +d.cash) || 1, color: colors.cash }
      ];
      const margin = { top: 20, right: 16, bottom: 26, left: 54 };
      const x = d3.scaleLinear().domain([0, 1]).range([margin.left, width - margin.right]);
      const y = d3.scaleBand().domain(data.map(d => d.label)).range([margin.top, height - margin.bottom]).padding(.32);
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y).tickSizeOuter(0));
      svg.selectAll("rect").data(data).join("rect")
        .attr("x", margin.left)
        .attr("y", d => y(d.label))
        .attr("width", d => x(d.value / d.max) - margin.left)
        .attr("height", y.bandwidth())
        .attr("fill", d => d.color)
        .attr("opacity", .84);
      svg.selectAll("text.value").data(data).join("text")
        .attr("x", d => x(d.value / d.max) + 6)
        .attr("y", d => y(d.label) + y.bandwidth() / 2 + 4)
        .attr("font-size", 12)
        .attr("fill", "#475569")
        .text(d => fmt(d.value));
    }

    function renderScenarioHeatmap() {
      const { width, height } = svgBox("#diagnosticSvg");
      const svg = d3.select("#diagnosticSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const table = [...DATA.scenario_tables["3"].map(d => ({ ...d, level: "L3" })), ...DATA.scenario_tables["4"].map(d => ({ ...d, level: "L4" }))];
      const cols = 20;
      const cell = Math.min((width - 42) / cols, 16);
      const startX = 28;
      const startY = 26;
      const color = d3.scaleLinear().domain([0, 3]).range(["#e8f5ec", "#a43f68"]);
      svg.append("text").attr("x", startX).attr("y", 16).attr("font-size", 12).attr("font-weight", 700).text("Scenario heatmap by storm count");
      svg.selectAll("rect")
        .data(table)
        .join("rect")
        .attr("x", (d, i) => startX + (i % cols) * cell)
        .attr("y", (d, i) => startY + Math.floor(i / cols) * cell)
        .attr("width", cell - 2)
        .attr("height", cell - 2)
        .attr("rx", 2)
        .attr("fill", d => d.feasible ? color(d.storm_count) : colors.route)
        .attr("stroke", d => d.level === "L3" ? "#fff" : "#cbd5e1")
        .on("mousemove", (event, d) => showTip(event, `${d.level} scenario ${d.scenario}<br>${d.feasible ? "feasible" : "blocked"}<br>storms ${d.storm_count}, hot ${d.hot_count}<br>objective ${fmt(d.objective, 1)}`))
        .on("mouseleave", hideTip);
    }

    function renderSourceFreshness() {
      const { width, height } = svgBox("#diagnosticSvg");
      const svg = d3.select("#diagnosticSvg").attr("viewBox", `0 0 ${width} ${height}`);
      const data = Object.entries(DATA.sources).map(([name, source]) => ({ name, bytes: source.bytes || 0, exists: source.exists }));
      const margin = { top: 22, right: 16, bottom: 32, left: 118 };
      const x = d3.scaleLinear().domain([0, d3.max(data, d => d.bytes) || 1]).range([margin.left, width - margin.right]);
      const y = d3.scaleBand().domain(data.map(d => d.name)).range([margin.top, height - margin.bottom]).padding(.24);
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y).tickSizeOuter(0));
      svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - margin.bottom})`).call(d3.axisBottom(x).ticks(4).tickFormat(d3.format(".2s")).tickSizeOuter(0));
      svg.selectAll("rect").data(data).join("rect")
        .attr("x", margin.left)
        .attr("y", d => y(d.name))
        .attr("width", d => x(d.bytes) - margin.left)
        .attr("height", y.bandwidth())
        .attr("fill", d => d.exists ? colors.blue : colors.route)
        .attr("opacity", .82);
    }

    function renderAll() {
      renderSummary();
      renderControls();
      renderRoute();
      renderTemporal();
      renderDiagnostics();
    }
    renderAll();
  </script>
</body>
</html>
"""
    path = output_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def generate_visual_outputs(output_root: Path) -> Dict[str, object]:
    figures = output_root / "figures"
    frontend = output_root / "frontend"
    traces: Dict[int, Mapping[str, object]] = {}
    figure_errors: List[Dict[str, str]] = []
    for level_id in (1, 2):
        trace_path = output_root / "solutions" / ("level_%s_trace.json" % level_id)
        trace = read_trace(trace_path)
        traces[level_id] = trace
        resource_path = figures / ("level_%s_resources.png" % level_id)
        path_path = figures / ("level_%s_path.png" % level_id)
        try:
            generate_resource_figure(trace, resource_path)
        except Exception as exc:  # pragma: no cover - depends on local matplotlib/Pillow install
            figure_errors.append(
                {
                    "figure": "level_%s_resources" % level_id,
                    "path": str(resource_path),
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            )
        try:
            generate_path_figure(level_id, trace, path_path)
        except Exception as exc:  # pragma: no cover - depends on local matplotlib/Pillow install
            figure_errors.append(
                {
                    "figure": "level_%s_path" % level_id,
                    "path": str(path_path),
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            )
    frontend_path = write_frontend(traces, output_root, frontend)
    summary_path = output_root / "report_tables" / "visualization_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "figures": sorted(str(path) for path in figures.glob("*.png")),
        "figure_errors": figure_errors,
        "frontend": str(frontend_path),
        "frontend_data": str(frontend / "dashboard-data.js"),
        "frontend_vendor": str(frontend / "vendor" / "d3.v7.min.js"),
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
