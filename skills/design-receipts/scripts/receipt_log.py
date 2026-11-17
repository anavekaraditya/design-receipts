"""Read and write the Markdown decision log and its derived index."""

import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path


INDEX_MARKER = "<!-- design-receipts:index v1 -->"
TEMPLATE_MARKER = "<!-- design-receipts:template v1 -->"
MISSING = "[verify]"
AI_ROLES = (
    "Proposed by AI",
    "Built by AI",
    "Verified by human",
    "Decided by human",
    "Overruled by human",
    "No AI involvement",
)
SECTIONS = {
    "context": "Context",
    "decision": "Decision",
    "options": "Options considered",
    "rejections": "Rejected options and why",
    "tradeoffs": "Trade-offs accepted",
    "outcome": "Outcome",
    "open_questions": "Open questions",
    "evidence": "Evidence",
}
REQUIRED = tuple(SECTIONS)[:5]
AUTHOR_FIELDS = {"title", "date", "ai_roles", *SECTIONS}
NUMBER = r"[0-9]+"
RECORD_NAME = re.compile(rf"({NUMBER})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
EVENT_NAME = re.compile(rf"({NUMBER})-(outcome|deprecation)-({NUMBER})\.md")
SCREENSHOT_NAME = re.compile(rf"({NUMBER})-screenshot-({NUMBER})")
SCREENSHOT_STATES = ("before", "after", "state")
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
PNG_END = b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
INDEX = "README.md"
TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "record-template.md"


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError("date must use YYYY-MM-DD")
    try:
        if date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError("date must use YYYY-MM-DD")


def has_outcome(value):
    value = value.casefold().strip().rstrip(".!?")
    placeholders = {"none", "unknown", "pending", "unmeasured", "not measured yet", "not yet measured", "not yet observed"}
    if not value or value in placeholders or value.startswith((MISSING, "to be observed")):
        return False
    return re.fullmatch(
        r"no (?:outcomes?|results?|measurements?) (?:(?:has|have|was|were) (?:been )?)?"
        r"(?:yet )?(?:recorded|observed|measured|provided|available)(?: yet)?",
        value,
    ) is None


def normalized_text(value, label, *, single_line=False):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in value or (single_line and len(value.splitlines()) > 1):
        raise ValueError(f"Invalid text for {label}")
    headings = "|".join(re.escape(title) for title in SECTIONS.values())
    if re.search(rf"^## (?:{headings})[ \t]*$", value, flags=re.MULTILINE):
        raise ValueError(f"{label} contains a reserved record heading. Use ### for nested headings.")
    return value


def canonical_id(raw):
    if isinstance(raw, int) and not isinstance(raw, bool):
        raw = str(raw)
    if not isinstance(raw, str) or not re.fullmatch(NUMBER, raw) or int(raw) < 1:
        raise ValueError(f"Invalid decision number {raw!r}")
    return f"{int(raw):04d}"


def display_id(record_id):
    return str(int(record_id))


def normalize_record(data):
    invalid = data.keys() - AUTHOR_FIELDS
    if invalid:
        raise ValueError(f"Unknown decision fields: {', '.join(sorted(invalid))}")
    roles = data.get("ai_roles", [])
    if not isinstance(roles, list) or any(role not in AI_ROLES for role in roles):
        raise ValueError(f"AI roles must be a list of: {', '.join(AI_ROLES)}")
    if len(set(roles)) != len(roles) or ("No AI involvement" in roles and len(roles) > 1):
        raise ValueError("Use distinct AI roles, or No AI involvement on its own")
    record = {
        "title": normalized_text(data.get("title", ""), "title", single_line=True) or MISSING,
        "date": iso_date(data.get("date", date.today().isoformat())),
        "ai_roles": roles,
    }
    for key, heading in SECTIONS.items():
        record[key] = normalized_text(data.get(key, ""), heading)
        if key in REQUIRED and not record[key]:
            record[key] = MISSING
    return record


def acceptance_gaps(record):
    def has_gap(value):
        return not value.strip() or MISSING in value.lower()

    gaps = [key for key in ("title", *REQUIRED) if has_gap(record[key])]
    if not record["ai_roles"]:
        gaps.append("ai_roles")
    options = record["options"]
    chosen = re.findall(r"^- Chosen: +\S.*$", options, flags=re.MULTILINE)
    alternatives = re.findall(r"^- Alternative: +\S.*$", options, flags=re.MULTILINE)
    constrained = re.findall(r"^- Constrained: +\S.*$", options, flags=re.MULTILINE)
    if (len(chosen) != 1 or not (alternatives or constrained) or (alternatives and constrained)) and "options" not in gaps:
        gaps.append("options")
    if "Overruled by human" in record["ai_roles"]:
        if not alternatives and "options" not in gaps:
            gaps.append("options")
        if re.match(r"^(?:-\s*)?none\b", record["rejections"], re.IGNORECASE) and "rejections" not in gaps:
            gaps.append("rejections")
    return gaps


def render_record(record):
    metadata = [
        f"# Decision {display_id(record['id'])} — {record['title']}",
        "",
        f"Date: {record['date']}",
        f"Status: {record['status']}",
        f"AI roles: {', '.join(record['ai_roles']) or MISSING}",
    ]
    if record["supersedes"]:
        metadata.append(f"Supersedes: {display_id(record['supersedes'])}")
    sections = [f"## {title}\n\n{record[key]}" for key, title in SECTIONS.items() if record[key]]
    return "\n\n".join(["\n".join(metadata), *sections]) + "\n"


def parse_record(path, record_id):
    raw = read_managed_text(path)
    titles = {heading: key for key, heading in SECTIONS.items()}
    matches = re.split(r"^## (" + "|".join(map(re.escape, titles)) + r")[ \t]*$", raw, flags=re.MULTILINE)
    lines = matches[0].strip().splitlines()
    title = re.fullmatch(rf"# (?:Decision )?({NUMBER}) — (.+)", lines[0]) if lines else None
    if not title or canonical_id(title[1]) != record_id:
        raise ValueError("heading must contain the matching decision number and title")
    fields = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or key in fields or key not in {"Date", "Status", "AI roles", "Supersedes"}:
            raise ValueError(f"Invalid record metadata: {line!r}")
        fields[key] = value.strip()
    status = fields.get("Status")
    if status not in ("proposed", "accepted") or "Date" not in fields or "AI roles" not in fields:
        raise ValueError("Date, Status (proposed or accepted), and AI roles metadata are required")
    roles = fields["AI roles"]
    data = {"title": title[2], "date": fields["Date"], "ai_roles": roles.split(", ") if roles != MISSING else []}
    for start in range(1, len(matches), 2):
        key = titles[matches[start]]
        if key in data:
            raise ValueError(f"Duplicate section: {matches[start]}")
        data[key] = matches[start + 1]
    if any(key not in data for key in REQUIRED):
        raise ValueError("Missing required headings. Use the template and mark unknowns [verify].")
    supersedes = canonical_id(fields["Supersedes"]) if "Supersedes" in fields else None
    record = normalize_record(data)
    gaps = acceptance_gaps(record)
    if status == "accepted" and gaps:
        raise ValueError(f"Accepted decision has gaps: {', '.join(gaps)}")
    return dict(record, id=record_id, path=path, status=status, effective_status=status, supersedes=supersedes)


def render_event(event):
    label = event["kind"].capitalize()
    return f"# {label} for Decision {display_id(event['record_id'])}\n\nDate: {event['date']}\n\n{event['text']}\n"


def parse_event(path, event_id, kind, record_id):
    lines = read_managed_text(path).splitlines()
    heading = re.fullmatch(rf"# {kind.capitalize()} for (?:Decision )?({NUMBER})", lines[0]) if lines else None
    if (len(lines) < 5 or not heading or canonical_id(heading[1]) != record_id
            or lines[1] or not lines[2].startswith("Date: ") or lines[3]):
        raise ValueError(f"Expected a {kind} heading, date, and text")
    body = normalized_text("\n".join(lines[4:]), "event")
    if not body or MISSING in body.lower():
        raise ValueError("An event needs a known outcome or reason")
    return dict(id=event_id, record_id=record_id, kind=kind, text=body, date=iso_date(lines[2][6:]), path=path)


def png_dimensions(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular PNG file at {path}")
    size = path.stat().st_size
    if not 57 <= size <= 32 * 1024 * 1024:
        raise ValueError("Screenshot must be a PNG of at most 32 MiB")
    with path.open("rb") as image:
        header = image.read(24)
        image.seek(-len(PNG_END), os.SEEK_END)
        if not header.startswith(PNG_HEADER) or image.read() != PNG_END:
            raise ValueError("Screenshot must be a complete PNG")
    width, height = struct.unpack(">II", header[16:24])
    if not width or not height:
        raise ValueError("Screenshot dimensions must be positive")
    return f"{width}x{height}"


def screenshot_fields(state, route, viewport, caption):
    if state not in SCREENSHOT_STATES:
        raise ValueError("Screenshot state must be before, after, or state")
    route = normalized_text(route, "route", single_line=True)
    if (not route.startswith("/") or route.startswith("//") or any(c.isspace() for c in route)
            or any(c in route for c in "?#\\`")):
        raise ValueError("Screenshot route must be a local path such as /settings, without a query or fragment")
    if not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", viewport):
        raise ValueError("Screenshot viewport must use WIDTHxHEIGHT, for example 1440x900")
    caption = normalized_text(caption, "caption", single_line=True)
    if not caption:
        raise ValueError("Give the screenshot a caption describing the visible UI state")
    return dict(state=state, route=route, viewport=viewport, text=caption)


def render_screenshot(event):
    return (
        f"# Screenshot for Decision {display_id(event['record_id'])}\n\n"
        f"Date: {event['date']}\nState: {event['state']}\nRoute: {event['route']}\n"
        f"Viewport: {event['viewport']}\nCaption: {event['text']}\n\n"
        "![Screenshot](image.png)\n"
    )


def parse_screenshot(bundle, event_id, record_id):
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("Expected a screenshot directory")
    path = bundle / "README.md"
    image_path = bundle / "image.png"
    lines = read_managed_text(path).splitlines()
    fields = ("Date: ", "State: ", "Route: ", "Viewport: ", "Caption: ")
    heading = re.fullmatch(rf"# Screenshot for (?:Decision )?({NUMBER})", lines[0]) if lines else None
    if (len(lines) < 7 or not heading or canonical_id(heading[1]) != record_id or lines[1]
            or any(not line.startswith(field) for field, line in zip(fields, lines[2:7]))):
        raise ValueError("Screenshot metadata needs a date, state, route, viewport, and caption")
    captured, state, route, viewport, caption = (line[len(field):] for field, line in zip(fields, lines[2:7]))
    png_dimensions(image_path)
    return dict(
        id=event_id, record_id=record_id, kind="screenshot", date=iso_date(captured), path=path,
        image_path=image_path, **screenshot_fields(state, route, viewport, caption),
    )


def write_screenshot(event, source):
    bundle = event["path"].parent
    bundle.parent.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".design-receipts-", dir=bundle.parent))
    try:
        png = staging / "image.png"
        shutil.copyfile(source, png)
        png_dimensions(png)
        (staging / "README.md").write_text(render_screenshot(event), encoding="utf-8")
        staging.rename(bundle)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def read_managed_text(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file at {path}")
    return path.read_text(encoding="utf-8")


def confirm_managed(log):
    path = log / INDEX
    if not path.exists() and not path.is_symlink():
        template = log / "template.md"
        if template.is_file() and read_managed_text(template).split("\n", 1)[0] == TEMPLATE_MARKER:
            return
        raise ValueError(f"No initialized log at {log}. Run init or choose another --log-dir.")
    if read_managed_text(path).split("\n", 1)[0] != INDEX_MARKER:
        raise ValueError(f"Existing index at {path} belongs to another log. Choose another --log-dir.")


def check_lifecycle(records, events):
    successors = {}
    deprecations = set()
    for record in sorted(records.values(), key=lambda record: int(record["id"])):
        prior_id = record["supersedes"]
        if not prior_id:
            continue
        prior = records.get(prior_id)
        if not prior or prior["status"] != "accepted" or prior_id == record["id"]:
            raise ValueError(f"Decision {display_id(record['id'])} references invalid predecessor {display_id(prior_id)}")
        if record["date"] < prior["date"]:
            raise ValueError(f"Decision {display_id(record['id'])} predates its predecessor {display_id(prior_id)}")
        if record["status"] == "accepted":
            if prior_id in successors:
                raise ValueError(f"Decision {display_id(prior_id)} has two accepted successors")
            successors[prior_id] = record["id"]
            prior["effective_status"] = "superseded"
    for start in successors:
        chain = {start}
        successor = successors[start]
        while successor in successors:
            if successor in chain:
                raise ValueError(f"Supersession cycle involving {start}")
            chain.add(successor)
            successor = successors[successor]
    for event in events:
        record_id = event["record_id"]
        record = records.get(record_id)
        if event["kind"] == "screenshot" and record:
            continue
        if not record or record["status"] != "accepted" or event["date"] < record["date"]:
            raise ValueError(f"Event {display_id(event['id'])} references an invalid decision {display_id(record_id)}")
        if event["kind"] == "deprecation":
            if record_id in deprecations or record_id in successors:
                raise ValueError(f"Conflicting retirement records for {record_id}")
            deprecations.add(record_id)
            record["effective_status"] = "deprecated"


def read_log(log):
    confirm_managed(log)
    records = {}
    for path in sorted(log.iterdir()):
        if not re.match(r"[0-9].*\.md$", path.name):
            continue
        named = RECORD_NAME.fullmatch(path.name)
        if not named:
            raise ValueError(f"Invalid decision filename: {path.name}")
        try:
            record_id = canonical_id(named[1])
            if record_id in records:
                raise ValueError(f"Duplicate decision number {display_id(record_id)}")
            records[record_id] = parse_record(path, record_id)
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc

    events = []
    events_dir = log / "events"
    if events_dir.is_symlink() or (events_dir.exists() and not events_dir.is_dir()):
        raise ValueError(f"Expected a directory at {events_dir}")
    event_ids = set()
    if events_dir.exists():
        for path in sorted(events_dir.iterdir()):
            screenshot = SCREENSHOT_NAME.fullmatch(path.name)
            if not screenshot and not path.name.endswith(".md"):
                continue
            try:
                if screenshot:
                    event_id, record_id = map(canonical_id, screenshot.groups())
                    event = parse_screenshot(path, event_id, record_id)
                else:
                    named = EVENT_NAME.fullmatch(path.name)
                    if not named:
                        raise ValueError("Invalid event filename")
                    event_id, record_id = canonical_id(named[1]), canonical_id(named[3])
                    event = parse_event(path, event_id, named[2], record_id)
                if event_id in event_ids:
                    raise ValueError(f"Duplicate event number {event_id}")
                events.append(event)
                event_ids.add(event_id)
            except ValueError as exc:
                raise ValueError(f"{path.name}: {exc}") from exc
    events.sort(key=lambda event: int(event["id"]))
    check_lifecycle(records, events)
    return records, events


def render_index(records, events=()):
    lines = [
        INDEX_MARKER, "# Design decisions", "",
        "This index is generated from the decisions and their dated events.", "",
        "| Decision | Title | Status | Date | Links |", "| --- | --- | --- | --- | --- |",
    ]
    successors = {r["supersedes"]: r for r in records.values() if r["supersedes"] and r["status"] == "accepted"}
    screenshots = {}
    for event in events:
        if event["kind"] == "screenshot":
            screenshots.setdefault(event["record_id"], []).append(event)
    for record in sorted(records.values(), key=lambda item: int(item["id"])):
        record_id = record["id"]
        title = record["title"].replace("|", "\\|")
        status = record["effective_status"]
        links = []
        if record["supersedes"]:
            prior = records[record["supersedes"]]
            label = "Supersedes" if record["status"] == "accepted" else "Proposed successor to"
            links.append(f"{label} [Decision {display_id(prior['id'])}]({prior['path'].name})")
        if record_id in successors:
            successor = successors[record_id]
            links.append(f"Replaced by [Decision {display_id(successor['id'])}]({successor['path'].name})")
        for shot in screenshots.get(record_id, ()):
            label = shot["state"].capitalize()
            links.append(f"[{label} screenshot](events/{shot['path'].parent.name}/README.md)")
        link_text = ", ".join(links)
        lines.append(f"| [Decision {display_id(record_id)}]({record['path'].name}) | {title} | {status} | {record['date']} | {link_text} |")
    return "\n".join(lines) + "\n"


def next_id(identifiers):
    return f"{max(map(int, identifiers), default=0) + 1:04d}"


def filename_for(record):
    slug = re.sub(r"[^a-z0-9]+", "-", record["title"].casefold()).strip("-")[:72].rstrip("-")
    return f"{display_id(record['id'])}-{slug or 'decision'}.md"


@contextmanager
def write_lock(log):
    lock = log.parent / f".design-receipts-{log.name}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 5
    while True:
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError(f"Log is busy ({lock}). If a writer was interrupted, verify it has exited before clearing the lock.") from None
            time.sleep(0.05)
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def write_atomic(path, content):
    descriptor, temp = tempfile.mkstemp(prefix=".design-receipts-", dir=path.parent)
    pending = Path(temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def initialize(log, track, root):
    with write_lock(log):
        if log.exists() and (not log.is_dir() or any(log.iterdir())):
            confirm_managed(log)
            return False
        relative = log.relative_to(root).as_posix()
        indexed = subprocess.run(
            ["git", "ls-files", "-z", "--", f":(literal){relative}/"],
            cwd=root, check=True, capture_output=True, timeout=5,
        ).stdout
        if indexed:
            raise ValueError(f"Git already tracks files at {relative}. Restore that log or choose another --log-dir.")
        pending = Path(tempfile.mkdtemp(prefix=".design-receipts-", dir=log.parent))
        try:
            (pending / INDEX).write_text(render_index({}), encoding="utf-8")
            shutil.copyfile(TEMPLATE, pending / "template.md")
            if not track:
                (pending / ".gitignore").write_text("# Private Design Receipts log and drafts\n*\n", encoding="utf-8")
            if log.exists():
                log.rmdir()
            pending.rename(log)
        finally:
            if pending.exists():
                shutil.rmtree(pending)
    return True
