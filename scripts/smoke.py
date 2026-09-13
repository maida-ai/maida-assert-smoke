"""Exercise the released CLI in an isolated copy; retain reviewable reports."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "good": ("pass", 0),
    "harmless_copy_edit": ("pass", 0),
    "extra_research": ("fail", 1),
    "retry_loop": ("fail", 1),
    "missing_followup": ("fail", 1),
    "unreviewed_send": ("fail", 1),
    "tool_error": ("fail", 1),
    "token_spike": ("fail", 1),
    "inconclusive": ("inconclusive", 0),
}


def run(command, cwd, env):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def sandbox(directory):
    project = directory / "project"
    project.mkdir()
    for name in ("agent.py", "scenario.json"):
        shutil.copyfile(ROOT / name, project / name)
    for name in ("sales_agent", "fixtures", ".maida"):
        shutil.copytree(
            ROOT / name, project / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    home = directory / "home"
    home.mkdir()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "USER": "smoke-fixture",
        "LOGNAME": "smoke-fixture",
        "LANG": "C.UTF-8",
        "MAIDA_DATA_DIR": str(directory / "runs"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    initialized = run(["git", "init", "--quiet"], project, env)
    if initialized.returncode:
        raise RuntimeError(initialized.stderr)
    return project, env


def capture_baseline(output):
    if output.exists():
        raise ValueError(
            "Baseline already exists; use reviewed maida accept to update it"
        )
    with tempfile.TemporaryDirectory(prefix="sales-baseline-") as directory:
        project, env = sandbox(Path(directory))
        env["SALES_SCENARIO"] = "good"
        report_path = project / "baseline-report.json"
        result = run(
            [
                "maida",
                "run",
                "agent.py",
                "--policy",
                ".maida/bootstrap.yaml",
                "--json-out",
                str(report_path),
            ],
            project,
            env,
        )
        if (
            result.returncode
            or json.loads(report_path.read_text())["verdict"] != "pass"
        ):
            raise RuntimeError(result.stdout + result.stderr)
        output.parent.mkdir(parents=True, exist_ok=True)
        result = run(
            [
                "maida",
                "baseline",
                "--from-report",
                str(report_path),
                "--out",
                str(output.resolve()),
            ],
            project,
            env,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)


def matrix(output):
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    with tempfile.TemporaryDirectory(prefix="sales-smoke-") as directory:
        project, env = sandbox(Path(directory))
        baseline = ".maida/baselines/sales.json"
        for scenario, (expected, expected_exit) in EXPECTED.items():
            env["SALES_SCENARIO"] = "good" if scenario == "inconclusive" else scenario
            policy = (
                ".maida/inconclusive.yaml"
                if scenario == "inconclusive"
                else ".maida/policy.yaml"
            )
            sidecar = Path(directory) / f"{scenario}.json"
            result = run(
                [
                    "maida",
                    "run",
                    "agent.py",
                    "--baseline",
                    baseline,
                    "--policy",
                    policy,
                    "--format",
                    "markdown",
                    "--json-out",
                    str(sidecar),
                ],
                project,
                env,
            )
            (output / f"{scenario}.md").write_text(result.stdout)
            (output / f"{scenario}.stderr.txt").write_text(result.stderr)
            report = json.loads(sidecar.read_text()) if sidecar.exists() else {}
            (output / f"{scenario}.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            verdict = report.get("verdict")
            checks = {
                item["check_name"]: item["verdict"]
                for item in report.get("aggregate_results", [])
            }
            summary.append(
                {
                    "scenario": scenario,
                    "expected": expected,
                    "verdict": verdict,
                    "exit_code": result.returncode,
                    "matched": verdict == expected
                    and result.returncode == expected_exit,
                    "checks": checks,
                }
            )
        # Reviewed structural change: accept only in the disposable copy and rerun.
        env["SALES_SCENARIO"] = "extra_research"
        recorded = run(["python", "agent.py"], project, env)
        accepted = run(
            [
                "maida",
                "accept",
                "--baseline",
                baseline,
                "--reason",
                "Synthetic smoke: reviewed comparison step",
            ],
            project,
            env,
        )
        sidecar = Path(directory) / "accepted.json"
        rerun = run(
            [
                "maida",
                "run",
                "agent.py",
                "--baseline",
                baseline,
                "--policy",
                ".maida/policy.yaml",
                "--format",
                "markdown",
                "--json-out",
                str(sidecar),
            ],
            project,
            env,
        )
        report = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        (output / "accepted.json").write_text(json.dumps(report, indent=2) + "\n")
        (output / "accept.log").write_text(
            recorded.stdout + recorded.stderr + accepted.stdout + accepted.stderr
        )
        (output / "accepted.md").write_text(rerun.stdout)
        (output / "accepted-baseline.json").write_text((project / baseline).read_text())
        summary.append(
            {
                "scenario": "accepted_extra_research",
                "expected": "pass",
                "verdict": report.get("verdict"),
                "exit_code": rerun.returncode,
                "matched": recorded.returncode
                == accepted.returncode
                == rerun.returncode
                == 0
                and report.get("verdict") == "pass",
            }
        )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for item in summary:
        print(f"{item['scenario']}: {item['verdict']} (expected {item['expected']})")
    return 0 if all(item["matched"] for item in summary) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "smoke")
    parser.add_argument("--capture-baseline", type=Path)
    args = parser.parse_args()
    if args.capture_baseline:
        capture_baseline(args.capture_baseline)
        print(f"Captured known-good baseline: {args.capture_baseline}")
        return 0
    return matrix(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
