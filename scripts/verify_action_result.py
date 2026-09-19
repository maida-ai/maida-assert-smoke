"""Verify expected report-only behavior and fresh GitHub check publication."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.smoke import EXPECTED


def verify(directory: Path, scenario: str, head_sha: str, run_url: str) -> int:
    def read(name):
        return json.loads((directory / name).read_text())

    report = read("maida-report.json")
    expected = EXPECTED[scenario][0]
    if report["verdict"] != expected:
        raise ValueError(
            f"{scenario}: expected verdict {expected}, got {report['verdict']}"
        )
    if not (directory / "maida-report.md").read_text().strip():
        raise ValueError("Markdown report is empty")

    payload = read("maida-check-payload.json")
    name = "Maida behavioral report (non-blocking)"
    for key, value in {
        "name": name,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "neutral",
        "details_url": run_url,
    }.items():
        if payload[key] != value:
            raise ValueError(f"Unexpected check {key}: expected {value!r}")
    if payload["output"]["title"] != f"{name}: {expected.upper()}":
        raise ValueError("Check title does not preserve the expected verdict")
    if run_url not in payload["output"]["summary"]:
        raise ValueError("Check summary does not identify this workflow run")

    previous_ids = {
        check["id"]
        for page in read("checks-before.json")
        for check in page["check_runs"]
    }
    # GitHub can replace details_url with its check URL. Match the output,
    # including the workflow link in the summary, and exclude earlier attempts.
    matches = [
        check
        for page in read("checks-after.json")
        for check in page["check_runs"]
        if check["id"] not in previous_ids
        and all(
            check.get(key) == payload[key]
            for key in ("name", "head_sha", "status", "conclusion")
        )
        and all(
            check.get("output", {}).get(key) == payload["output"][key]
            for key in ("title", "summary")
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one new matching published check, found {len(matches)}"
        )
    return matches[0]["id"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=EXPECTED)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        check_id = verify(args.directory, args.scenario, args.head_sha, args.run_url)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Action smoke verification failed: {error}", file=sys.stderr)
        return 1
    print(
        f"{args.scenario}: expected {EXPECTED[args.scenario][0]}; published check {check_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
