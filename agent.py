"""Entry point used unchanged by the local CLI and the GitHub Action."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from sales_agent import SCENARIOS, run_sales_agent


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS)
    args = parser.parse_args()
    scenario = (
        args.scenario
        or os.environ.get("SALES_SCENARIO")
        or json.loads((root / "scenario.json").read_text())["scenario"]
    )
    lead = json.loads((root / "fixtures" / "lead.json").read_text())
    print(json.dumps(asdict(run_sales_agent(lead, scenario)), indent=2))


if __name__ == "__main__":
    main()
