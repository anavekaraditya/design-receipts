"""Replay a fictional project with the Design Receipts CLI."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


EXAMPLE = Path(__file__).resolve().parent
CLI = EXAMPLE.parents[1] / "skills/design-receipts/scripts/receipts.py"

INITIAL = {
    "title": "Reveal arrivals on tap",
    "date": "2026-11-05",
    "context": (
        "Routeboard helps riders find their stop before they check its arrivals. "
        "The route list needs to stay easy to scan."
    ),
    "decision": "Show arrivals when a rider taps a stop.",
    "options": (
        "- Chosen: Reveal arrivals for a stop when tapped.\n"
        "- Alternative: Show arrival predictions under every stop."
    ),
    "rejections": "Inline arrivals compete with the stop names riders are scanning for.",
    "tradeoffs": "Checking the next arrival takes one additional tap.",
    "ai_roles": ["Proposed by AI", "Overruled by human"],
}

SUCCESSOR = {
    "title": "Show the next arrival for the selected stop",
    "date": "2026-11-07",
    "context": "Riders who already selected a stop still have to open it to check the next arrival.",
    "decision": "Show one arrival for the selected stop. Keep the other rows collapsed.",
    "options": (
        "- Chosen: Show a prediction only for the selected stop.\n"
        "- Alternative: Automatically expand the first row."
    ),
    "rejections": "The first row might show a stop the rider has not selected.",
    "tradeoffs": "The selected row uses one extra line in the route list.",
    "ai_roles": ["Decided by human", "Built by AI"],
    "open_questions": "Can riders spot the next arrival without losing their place in the list?",
}

OUTCOME = {
    "date": "2026-11-08",
    "text": (
        "The designer checked both states in the prototype. With a stop selected, "
        "that row showed one arrival and the other rows showed stop names. "
        "With no stop selected, every row showed stop names. Scanning speed was unmeasured."
    ),
}

PROPOSAL = {
    "title": "Add a hint to the stop rows",
    "date": "2026-11-08",
    "decision": "Explore a hint that explains how to open a stop.",
}


def run_receipts(project, *arguments, payload=None):
    command = [
        sys.executable,
        "-SB",
        str(CLI),
        "--project",
        str(project),
        "--log-dir",
        "decisions",
        *arguments,
    ]
    subprocess.run(
        command,
        input=None if payload is None else json.dumps(payload),
        check=True,
        text=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Path for a new, empty example project")
    project = parser.parse_args().project.resolve()
    if project.exists():
        parser.error("choose a path that does not exist")
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(project)], check=True)
    run_receipts(project, "init", "--track")
    run_receipts(project, "capture", payload=INITIAL)
    run_receipts(project, "accept", "0001", "--confirmed")
    run_receipts(project, "capture", "--confirmed", "--supersedes", "0001", payload=SUCCESSOR)
    run_receipts(project, "outcome", "0002", "--confirmed", payload=OUTCOME)
    run_receipts(project, "capture", payload=PROPOSAL)
    run_receipts(project, "validate")
    run_receipts(
        project,
        "compile",
        "--narrative",
        "-",
        "--output",
        "case-study.md",
        payload=json.loads((EXAMPLE / "narrative.json").read_text(encoding="utf-8")),
    )
    print(project / "decisions/README.md")


if __name__ == "__main__":
    main()
