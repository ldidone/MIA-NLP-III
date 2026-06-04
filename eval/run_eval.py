"""Evaluation harness for CompuFix Agents.

Runs the triage + planner pipeline over labeled test cases and reports:
    * triage accuracy (predicted problem type == expected),
    * expected-tool coverage (expected tool appears in the action plan),
    * approval-decision accuracy (the expected tool's approval flag matches),
    * package-mapping accuracy (when an expected package is provided).

Usage:
    python eval/run_eval.py
    python eval/run_eval.py --cases path/to/test_cases.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the 'src' layout importable when run as a plain script.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from compufix_agents.agents.planner_agent import plan_actions  # noqa: E402
from compufix_agents.agents.triage_agent import triage  # noqa: E402
from compufix_agents.schemas.plan import ActionPlan  # noqa: E402

DEFAULT_CASES = _ROOT / "eval" / "test_cases.json"


def _find_step(plan: ActionPlan, tool: str):
    """Return the first plan step using ``tool``, or ``None``."""
    return next((s for s in plan.plan if s.tool == tool), None)


def _package_in_plan(plan: ActionPlan, package: str) -> bool:
    """Return True if any step references the expected package name."""
    for step in plan.plan:
        if step.args.get("package_name") == package:
            return True
    return False


def evaluate(cases: list[dict]) -> dict:
    """Evaluate all cases and return aggregate metrics + per-case records."""
    records: list[dict] = []
    triage_hits = 0
    tool_hits = 0
    approval_hits = 0
    package_total = 0
    package_hits = 0

    for case in cases:
        text = case["input"]
        # Force the deterministic path so eval is reproducible offline.
        tr = triage(text, use_llm=False)
        plan = plan_actions(tr)

        expected_type = case["expected_problem_type"]
        triage_ok = tr.problem_type.value == expected_type
        triage_hits += int(triage_ok)

        expected_tool = case.get("expected_tool")
        step = _find_step(plan, expected_tool) if expected_tool else None
        tool_ok = step is not None
        tool_hits += int(tool_ok)

        expected_approval = case.get("requires_approval")
        approval_ok = step is not None and step.requires_approval == expected_approval
        approval_hits += int(approval_ok)

        package_ok: bool | None = None
        if "expected_package" in case:
            package_total += 1
            package_ok = _package_in_plan(plan, case["expected_package"])
            package_hits += int(package_ok)

        records.append(
            {
                "input": text,
                "expected_type": expected_type,
                "predicted_type": tr.problem_type.value,
                "triage_ok": triage_ok,
                "expected_tool": expected_tool,
                "tool_ok": tool_ok,
                "expected_approval": expected_approval,
                "approval_ok": approval_ok,
                "expected_package": case.get("expected_package"),
                "package_ok": package_ok,
            }
        )

    n = len(cases)
    metrics = {
        "n_cases": n,
        "triage_accuracy": triage_hits / n if n else 0.0,
        "tool_coverage": tool_hits / n if n else 0.0,
        "approval_accuracy": approval_hits / n if n else 0.0,
        "package_accuracy": (package_hits / package_total) if package_total else None,
    }
    return {"metrics": metrics, "records": records}


def _print_report(report: dict) -> None:
    """Pretty-print the evaluation report to stdout."""
    print("=" * 78)
    print("CompuFix Agents — Evaluation")
    print("=" * 78)
    header = f"{'input':<48} {'triage':<7} {'tool':<6} {'appr':<6} {'pkg':<5}"
    print(header)
    print("-" * 78)
    for r in report["records"]:

        def mark(ok):  # noqa: ANN001 - tiny local helper
            return "  -  " if ok is None else ("PASS" if ok else "FAIL")

        text = (r["input"][:45] + "...") if len(r["input"]) > 45 else r["input"]
        print(
            f"{text:<48} {mark(r['triage_ok']):<7} {mark(r['tool_ok']):<6} "
            f"{mark(r['approval_ok']):<6} {mark(r['package_ok']):<5}"
        )
        if not r["triage_ok"]:
            print(f"    expected={r['expected_type']} predicted={r['predicted_type']}")

    m = report["metrics"]
    print("-" * 78)
    print(f"Cases evaluated     : {m['n_cases']}")
    print(f"Triage accuracy     : {m['triage_accuracy']:.0%}")
    print(f"Expected-tool found : {m['tool_coverage']:.0%}")
    print(f"Approval accuracy   : {m['approval_accuracy']:.0%}")
    if m["package_accuracy"] is not None:
        print(f"Package mapping     : {m['package_accuracy']:.0%}")
    print("=" * 78)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate CompuFix triage + planner.")
    parser.add_argument(
        "--cases", type=Path, default=DEFAULT_CASES, help="Path to the test cases JSON file."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the full report as JSON instead of a table."
    )
    args = parser.parse_args(argv)

    if not args.cases.exists():
        print(f"Test cases file not found: {args.cases}", file=sys.stderr)
        return 1

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = evaluate(cases)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)

    # Exit non-zero if triage accuracy is below a basic threshold.
    return 0 if report["metrics"]["triage_accuracy"] >= 0.8 else 2


if __name__ == "__main__":
    raise SystemExit(main())
