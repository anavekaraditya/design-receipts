"""Command-line entry point for the Design Receipts skill."""

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from compile_receipts import add_commands
from receipt_log import (
    AUTHOR_FIELDS,
    INDEX,
    MISSING,
    SCREENSHOT_STATES,
    acceptance_gaps,
    canonical_id,
    check_lifecycle,
    confirm_managed,
    filename_for,
    has_outcome,
    initialize,
    iso_date,
    next_id,
    normalize_record,
    normalized_text,
    png_dimensions,
    read_log,
    read_managed_text,
    render_event,
    render_index,
    render_record,
    screenshot_fields,
    write_atomic,
    write_lock,
    write_screenshot,
)


def project_and_log(project, log_dir):
    git = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False, timeout=5,
    )
    if git.returncode:
        raise ValueError(f"Choose a Git project with --project. No worktree found at {project}.")
    root = Path(git.stdout.rstrip("\r\n")).resolve()
    relative = Path(log_dir)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("--log-dir must name a directory inside the Git worktree")
    log = root / relative
    if log.resolve() != log or any(part.casefold() == ".git" for part in relative.parts):
        raise ValueError("--log-dir must avoid symbolic links and Git metadata")
    return root, log


def input_object():
    if sys.stdin.isatty():
        raise ValueError("Provide the command's JSON object on standard input")
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Expected a JSON object on standard input: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object on standard input")
    return data


def get_record(records, record_id):
    canonical_id(record_id)
    if record_id not in records:
        raise ValueError(f"Receipt {record_id} does not exist. Run review to find the number.")
    return records[record_id]


def check_predecessor(records, record):
    if record["supersedes"]:
        prior = get_record(records, record["supersedes"])
        if prior["effective_status"] != "accepted":
            raise ValueError(f"Receipt {prior['id']} must be currently accepted to be superseded")


def refresh_index(log, records, events):
    write_atomic(log / INDEX, render_index(records, events))


def index_after_save(path, log, records, events):
    try:
        refresh_index(log, records, events)
    except OSError as exc:
        raise ValueError(f"Saved {path}, but could not refresh the index. Run reindex to repair it: {exc}") from exc


def init_command(args, root, log):
    if initialize(log, args.track, root):
        privacy = "ready to track in Git" if args.track else "Git-ignored by default"
        print(f"Initialized {log.relative_to(root)} ({privacy}).")
    else:
        print(f"Using the existing log at {log.relative_to(root)}.")


def capture(args, root, log):
    records, events = read_log(log)
    authored = normalize_record(input_object())
    record_id = next_id(records)
    gaps = acceptance_gaps(authored)
    status = "accepted" if args.confirmed and not gaps else "proposed"
    for key in gaps:
        if key != "ai_roles" and MISSING not in authored[key].lower():
            authored[key] += f"\n\n{MISSING}" if key != "title" else f" {MISSING}"
    record = dict(authored, id=record_id, status=status, effective_status=status, supersedes=args.supersedes)
    check_predecessor(records, record)
    path = log / filename_for(record)
    record["path"] = path
    records[record_id] = record
    check_lifecycle(records, events)
    write_atomic(path, render_record(record))
    index_after_save(path, log, records, events)
    print(f"Saved {record_id} as {status} at {path.relative_to(root)}.")
    if gaps:
        print(f"Needs review: {', '.join(gaps)}.")


def accept(args, root, log):
    records, events = read_log(log)
    record = get_record(records, args.record_id)
    if record["status"] != "proposed":
        raise ValueError(f"Receipt {record['id']} has already been accepted")
    fields = {key: record[key] for key in AUTHOR_FIELDS}
    if args.update:
        fields.update(input_object())
    authored = normalize_record(fields)
    gaps = acceptance_gaps(authored)
    if gaps:
        raise ValueError(f"Receipt {record['id']} is still proposed. Complete: {', '.join(gaps)}.")
    record.update(authored, status="accepted", effective_status="accepted")
    check_predecessor(records, record)
    check_lifecycle(records, events)
    write_atomic(record["path"], render_record(record))
    index_after_save(record["path"], log, records, events)
    print(f"Accepted {record['id']} at {record['path'].relative_to(root)}.")


def add_event(args, root, log):
    records, events = read_log(log)
    record = get_record(records, args.record_id)
    kind = args.event_kind
    if record["status"] != "accepted" or (kind == "deprecation" and record["effective_status"] != "accepted"):
        raise ValueError(f"Cannot add a {kind} entry to a {record['effective_status']} receipt")
    data = input_object()
    if data.keys() - {"text", "date"}:
        raise ValueError("Event JSON accepts text and an optional date")
    body = normalized_text(data.get("text", ""), kind)
    if not body or MISSING in body.lower() or (kind == "outcome" and not has_outcome(body)):
        raise ValueError("Provide a known observation or reason")
    event_id = next_id(event["id"] for event in events)
    path = log / "events" / f"{event_id}-{kind}-{record['id']}.md"
    event = {
        "id": event_id, "record_id": record["id"], "kind": kind, "path": path,
        "date": iso_date(data.get("date", date.today().isoformat())), "text": body,
    }
    events.append(event)
    check_lifecycle(records, events)
    path.parent.mkdir(exist_ok=True)
    write_atomic(path, render_event(event))
    index_after_save(path, log, records, events)
    print(f"Saved {kind} for {record['id']} at {path.relative_to(root)}.")


def attach_screenshot(args, root, log):
    records, events = read_log(log)
    record = get_record(records, args.record_id)
    source = root / args.png
    dimensions = png_dimensions(source)
    fields = screenshot_fields(args.state, args.route, args.viewport or dimensions, args.caption)
    captured = iso_date(args.date) if args.date else date.today().isoformat()

    event_id = next_id(event["id"] for event in events)
    bundle = log / "events" / f"{event_id}-screenshot-{record['id']}"
    event = dict(
        id=event_id, record_id=record["id"], kind="screenshot", date=captured, path=bundle / "README.md",
        image_path=bundle / "image.png", **fields,
    )
    write_screenshot(event, source)
    events.append(event)
    index_after_save(event["path"], log, records, events)
    print(f"Attached {args.state} screenshot to {record['id']} at {event['image_path'].relative_to(root)}.")


def review(args, root, log):
    records, events = read_log(log)
    if not records:
        print("No receipts yet. Capture a design decision to start the log.")
        return
    outcomes = {event["record_id"] for event in events if event["kind"] == "outcome"}
    screenshots = Counter(event["record_id"] for event in events if event["kind"] == "screenshot")
    for status in ("proposed", "accepted", "superseded", "deprecated"):
        group = [record for record in records.values() if record["effective_status"] == status]
        if not group:
            continue
        print(f"{status.capitalize()} ({len(group)})")
        for record in sorted(group, key=lambda item: int(item["id"])):
            follow_up = ""
            if status == "proposed":
                gaps = acceptance_gaps(record)
                follow_up = f" (complete {', '.join(gaps)})" if gaps else " (awaiting confirmation)"
            if status == "accepted" and record["id"] not in outcomes and not has_outcome(record["outcome"]):
                follow_up = " (outcome pending)"
            count = screenshots[record["id"]]
            if count:
                follow_up += f" · {count} screenshot{'s' if count != 1 else ''}"
            print(f"  {record['id']}  {record['title']}{follow_up}")


def validate(args, root, log):
    records, events = read_log(log)
    index = log / INDEX
    if not index.exists() or read_managed_text(index) != render_index(records, events):
        raise ValueError("Decision index is missing or stale. Run reindex to rebuild it.")
    print(f"Valid log: {len(records)} receipt(s), {len(events)} event(s).")


def reindex(args, root, log):
    records, events = read_log(log)
    refresh_index(log, records, events)
    print(f"Rebuilt {log.relative_to(root) / INDEX}.")


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="path inside the Git project")
    parser.add_argument("--log-dir", default="docs/decisions", help="log location relative to the Git root")
    commands = parser.add_subparsers(required=True, dest="command")
    init = commands.add_parser("init", help="create a project log")
    init.add_argument("--track", action="store_true", help="leave the new log visible to Git")
    init.set_defaults(handler=init_command)
    new = commands.add_parser("capture", help="save receipt JSON from stdin")
    new.add_argument("--confirmed", action="store_true", help="the designer confirmed these exact details")
    new.add_argument("--supersedes", metavar="ID", help="existing receipt this decision replaces")
    new.set_defaults(handler=capture)
    approval = commands.add_parser("accept", help="accept a proposed receipt")
    approval.add_argument("record_id")
    approval.add_argument("--confirmed", action="store_true", required=True)
    approval.add_argument("--update", action="store_true", help="read updated authored fields as JSON from stdin")
    approval.set_defaults(handler=accept)
    replacement = commands.add_parser("supersede", help="replace an accepted receipt with confirmed JSON from stdin")
    replacement.add_argument("supersedes", metavar="ID")
    replacement.add_argument("--confirmed", action="store_true", required=True)
    replacement.set_defaults(handler=capture)
    for command, kind in (("outcome", "outcome"), ("deprecate", "deprecation")):
        event = commands.add_parser(command, help=f"append a dated {kind} from JSON on stdin")
        event.add_argument("record_id")
        event.add_argument("--confirmed", action="store_true", required=True)
        event.set_defaults(handler=add_event, event_kind=kind)
    screenshot = commands.add_parser("attach-screenshot", help="attach a local PNG to a receipt")
    screenshot.add_argument("record_id")
    screenshot.add_argument("png", type=Path)
    screenshot.add_argument("--state", choices=SCREENSHOT_STATES, required=True)
    screenshot.add_argument("--route", required=True, help="local route path without query or fragment")
    screenshot.add_argument("--viewport", help="CSS viewport as WIDTHxHEIGHT; defaults to the PNG dimensions")
    screenshot.add_argument("--caption", required=True, help="what the screenshot visibly shows")
    screenshot.add_argument("--date", help="screenshot capture day as YYYY-MM-DD")
    screenshot.set_defaults(handler=attach_screenshot)
    for handler, help_text in (
        (review, "show decisions by status and flag follow-ups"),
        (validate, "check the Markdown log and index"),
        (reindex, "rebuild the decision index"),
    ):
        commands.add_parser(handler.__name__, help=help_text).set_defaults(handler=handler)
    add_commands(commands)
    return parser


def main():
    args = get_parser().parse_args()
    try:
        root, log = project_and_log(args.project, args.log_dir)
        if args.command == "init":
            return args.handler(args, root, log) or 0
        confirm_managed(log)
        with write_lock(log):
            return args.handler(args, root, log) or 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"design-receipts: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
