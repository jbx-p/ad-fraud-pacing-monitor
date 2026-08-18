"""
Daily automation wrapper.

Runs the three core analytical modules in sequence (pacing, fraud
detection, A/B testing) and consolidates their key findings into a
single "morning report" -- the kind of script an ad-ops analyst would
actually run every morning, or that a CI job would run on a schedule.

Run directly: python src/run_daily_check.py
Outputs: reports/morning_report.md (overwritten each run)
         reports/run_history.log (appended each run, never overwritten)
"""

import subprocess
import sys
from datetime import datetime

REPORT_PATH = "reports/morning_report.md"
LOG_PATH = "reports/run_history.log"

MODULES = [
    ("Pacing Health Check", "src/pacing.py", "reports/pacing_report.md"),
    ("Fraud & Anomaly Detection", "src/fraud_detection.py", "reports/fraud_report.md"),
    ("A/B Testing", "src/ab_testing.py", "reports/ab_test_report.md"),
]


def run_module(label, script_path):
    """
    Runs a module as a subprocess (not an import) so that a crash in one
    module doesn't take down the whole pipeline -- each module's success/
    failure is captured independently, which is how a real daily job
    should behave: one broken data source shouldn't silence every report.
    """
    print(f"\n{'='*60}")
    print(f"Running: {label}")
    print(f"{'='*60}")

    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
    )

    success = result.returncode == 0
    status = "SUCCESS" if success else "FAILED"
    print(f"[{status}] {label}")

    if not success:
        print(f"--- stderr ---\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")

    return {
        "label": label,
        "success": success,
        "stdout_tail": result.stdout[-3000:],
        "stderr_tail": result.stderr[-1000:] if not success else "",
    }


def extract_summary_line(report_path, keyword_lines=3):
    """
    Pulls the first few non-empty lines from a module's markdown report
    to embed a quick preview in the consolidated morning report, without
    duplicating the full report content.
    """
    try:
        with open(report_path, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        return lines[:keyword_lines]
    except FileNotFoundError:
        return ["(report not found -- module may have failed)"]


def generate_morning_report(run_results, timestamp):
    lines = []
    lines.append("# Morning Report — Ad Campaign Performance & Fraud Monitoring\n")
    lines.append(f"Generated: {timestamp}\n")

    lines.append("## Pipeline Status\n")
    lines.append("| Module | Status |")
    lines.append("|---|---|")
    for r in run_results:
        icon = "PASS" if r["success"] else "FAIL"
        lines.append(f"| {r['label']} | {icon} |")

    all_passed = all(r["success"] for r in run_results)
    lines.append(f"\n**Overall pipeline status: {'ALL CHECKS PASSED' if all_passed else 'ONE OR MORE CHECKS FAILED — see details below'}**\n")

    for (label, script_path, report_path), r in zip(MODULES, run_results):
        lines.append(f"\n## {label}\n")
        if r["success"]:
            preview = extract_summary_line(report_path)
            for line in preview:
                lines.append(f"> {line}")
            lines.append(f"\n[Full report]({report_path.replace('reports/', '')})")
        else:
            lines.append("**This module failed to run.** Last output captured:\n")
            lines.append("```")
            lines.append(r["stdout_tail"][-1500:])
            lines.append(r["stderr_tail"][-500:])
            lines.append("```")

    lines.append(f"\n---\n*Generated automatically by run_daily_check.py at {timestamp}*")

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


def append_run_log(run_results, timestamp):
    """
    Appends (never overwrites) a one-line summary per run to a persistent
    log file, so repeated runs build a visible history -- useful for
    spotting "the fraud check has failed 3 days in a row" style patterns
    that a single overwritten report would hide.
    """
    all_passed = all(r["success"] for r in run_results)
    status = "ALL_PASS" if all_passed else "SOME_FAILED"
    detail = ", ".join(f"{r['label']}={'OK' if r['success'] else 'FAIL'}" for r in run_results)

    with open(LOG_PATH, "a") as f:
        f.write(f"{timestamp} | {status} | {detail}\n")


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Starting daily check run at {timestamp}")

    run_results = []
    for label, script_path, report_path in MODULES:
        result = run_module(label, script_path)
        run_results.append(result)

    print("\nGenerating consolidated morning report...")
    generate_morning_report(run_results, timestamp)

    print("Appending to run history log...")
    append_run_log(run_results, timestamp)

    all_passed = all(r["success"] for r in run_results)
    print(f"\n{'='*60}")
    print(f"Daily check complete. Overall status: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print(f"Report: {REPORT_PATH}")
    print(f"Log: {LOG_PATH}")
    print(f"{'='*60}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
