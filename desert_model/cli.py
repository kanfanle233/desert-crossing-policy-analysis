"""Command line interface for the desert modeling backend."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

from .analyze import write_analysis_report
from .baseline import baseline_shortest_path_trace
from .config import DEFAULT_CONFIG_PATH, default_output_root, load_level_map, select_levels
from .excel_io import write_result_workbook, write_solve_status
from .extract import extract_sources
from .models import SolutionTrace
from .solver import solve_deterministic_level, write_trace_csv, write_trace_json
from .validate import validate_level, validate_trace
from .visualize import generate_visual_outputs


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to levels.json")
    parser.add_argument("--output", type=Path, default=default_output_root(), help="Output root")


def cmd_extract(args: argparse.Namespace) -> int:
    outputs = extract_sources(
        problem_docx=args.problem_docx,
        attachment_docx=args.attachment_docx,
        output_dir=args.output / "extracted",
    )
    for name, path in outputs.items():
        print("%s: %s" % (name, path))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    level_map = load_level_map(args.config)
    levels = select_levels(level_map, args.levels)
    exit_code = 0
    for level in levels:
        issues = validate_level(level, require_graph=args.require_graph)
        if issues:
            exit_code = 1
            print("Level %s %s: issues" % (level.level_id, level.name))
            for issue in issues:
                print("  - %s" % issue)
        else:
            print("Level %s %s: ok" % (level.level_id, level.name))
    return exit_code


def cmd_solve(args: argparse.Namespace) -> int:
    level_map = load_level_map(args.config)
    levels = select_levels(level_map, args.levels)
    traces: Dict[int, SolutionTrace] = {}
    status_dir = args.output / "solutions"
    exit_code = 0
    for level in levels:
        trace = solve_deterministic_level(
            level,
            ignore_review=args.ignore_review,
            max_states_per_bucket=args.max_states_per_bucket,
            max_purchase_options=args.max_purchase_options,
            purchase_step=args.purchase_step,
        )
        if args.baseline_fallback and not trace.feasible and trace.status == "infeasible":
            baseline = baseline_shortest_path_trace(level)
            if baseline.feasible:
                trace = baseline
        traces[level.level_id] = trace
        write_trace_json(trace, status_dir / ("level_%s_trace.json" % level.level_id))
        if trace.feasible:
            write_trace_csv(trace, status_dir / ("level_%s_trace.csv" % level.level_id))
            trace_issues = validate_trace(level, trace)
            if trace_issues:
                exit_code = 1
                print("Level %s solved but trace validation failed: %s" % (level.level_id, "; ".join(trace_issues)))
            else:
                print("Level %s solved: objective %.2f" % (level.level_id, trace.objective_value))
        else:
            exit_code = 1
            print("Level %s not solved: %s - %s" % (level.level_id, trace.status, trace.message))
    write_solve_status(args.output / "logs" / "solve_status.json", traces)
    result_levels = {k: v for k, v in traces.items() if k in (1, 2) and v.feasible}
    if result_levels:
        try:
            write_result_workbook(
                template_path=args.result_template,
                output_path=args.output / "result" / "Result_solved.xlsx",
                traces=result_levels,
            )
            print("Result workbook: %s" % (args.output / "result" / "Result_solved.xlsx"))
        except RuntimeError as exc:
            print("Result workbook skipped: %s" % exc)
    return exit_code


def cmd_analyze(args: argparse.Namespace) -> int:
    level_map = load_level_map(args.config)
    levels = select_levels(level_map, args.levels)
    report = write_analysis_report(levels, args.output / "report_tables", ignore_review=args.ignore_review)
    print("Analysis report: %s" % report)
    return 0


def cmd_visualize(args: argparse.Namespace) -> int:
    payload = generate_visual_outputs(args.output)
    print("Frontend: %s" % payload["frontend"])
    for figure in payload["figures"]:
        print("Figure: %s" % figure)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backend project for 2020B desert crossing modeling")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Extract source docx text/tables/VML summaries")
    extract.add_argument("--problem-docx", type=Path, default=Path("2020B-穿越沙漠.docx"))
    extract.add_argument("--attachment-docx", type=Path, default=Path("附件.docx"))
    _add_common_args(extract)
    extract.set_defaults(func=cmd_extract)

    validate = subparsers.add_parser("validate", help="Validate level config")
    validate.add_argument("--levels", default="all")
    validate.add_argument("--require-graph", action="store_true")
    _add_common_args(validate)
    validate.set_defaults(func=cmd_validate)

    solve = subparsers.add_parser("solve", help="Solve deterministic reviewed levels")
    solve.add_argument("--levels", default="1,2")
    solve.add_argument("--result-template", type=Path, default=Path("Result.xlsx"))
    solve.add_argument("--ignore-review", action="store_true", help="Allow solving a level marked review_required")
    solve.add_argument("--max-states-per-bucket", type=int, default=800)
    solve.add_argument("--max-purchase-options", type=int, default=500)
    solve.add_argument("--purchase-step", type=int, default=25, help="Purchase grid step in boxes")
    solve.add_argument("--no-baseline-fallback", action="store_false", dest="baseline_fallback")
    solve.set_defaults(baseline_fallback=True)
    _add_common_args(solve)
    solve.set_defaults(func=cmd_solve)

    analyze = subparsers.add_parser("analyze", help="Generate strategy/scenario report tables")
    analyze.add_argument("--levels", default="3,4,5,6")
    analyze.add_argument("--ignore-review", action="store_true")
    _add_common_args(analyze)
    analyze.set_defaults(func=cmd_analyze)

    visualize = subparsers.add_parser("visualize", help="Generate figures and static frontend dashboard")
    _add_common_args(visualize)
    visualize.set_defaults(func=cmd_visualize)

    return parser


def main(argv: object = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
