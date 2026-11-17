"""Select confirmed decision evidence and write a sourced Markdown draft."""

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import quote

from receipt_log import has_outcome, iso_date, read_log


CONFIRMED_STATUSES = ("accepted", "superseded", "deprecated")
KEYWORD_FIELDS = (
    "title", "context", "decision", "options", "rejections", "tradeoffs",
    "outcome", "open_questions", "evidence",
)
NARRATIVE_SECTIONS = ("overview", "problem", "constraints")
MARKDOWN_ESCAPES = str.maketrans({character: f"\\{character}" for character in r"\`*_[]<>()!&~"})


def add_commands(subparsers):
    evidence = subparsers.add_parser("evidence", help="Read confirmed evidence as JSON")
    evidence.set_defaults(handler=print_evidence)
    compile_command = subparsers.add_parser("compile", help="Write a case-study draft")
    compile_command.set_defaults(handler=compile_draft)
    for command in (evidence, compile_command):
        command.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
        command.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
        command.add_argument("--status", choices=CONFIRMED_STATUSES)
        command.add_argument("--keyword", help="Match a phrase in the record or its outcome notes")
    compile_command.add_argument("--narrative", help="Read narrative JSON from a file or '-' for stdin")
    compile_command.add_argument("--output", help="Choose an output path relative to the project, or absolute")
    compile_command.add_argument("--overwrite", action="store_true", help="Replace the chosen draft with approval")


def evidence_packet(args, root, log):
    filters = {"from": args.date_from, "to": args.date_to, "status": args.status, "keyword": args.keyword}
    for bound in (args.date_from, args.date_to):
        if bound is not None:
            try:
                iso_date(bound)
            except ValueError:
                raise ValueError(f"Expected an ISO date (YYYY-MM-DD), got {bound!r}") from None
    if args.date_from and args.date_to and args.date_from > args.date_to:
        raise ValueError("The start date must be on or before the end date")
    keyword = args.keyword.casefold().strip() if args.keyword is not None else None
    if keyword is not None and (not keyword or len(args.keyword.splitlines()) != 1):
        raise ValueError("The keyword must be a single line of text")

    records, events = read_log(log)
    outcome_text = {}
    for event in events:
        if event["kind"] == "outcome":
            outcome_text.setdefault(event["record_id"], []).append(event["text"])
    selected = []
    for key in sorted(records, key=int):
        record = records[key]
        if record["status"] != "accepted":
            continue
        if args.status and record["effective_status"] != args.status:
            continue
        if args.date_from and record["date"] < args.date_from:
            continue
        if args.date_to and record["date"] > args.date_to:
            continue
        searchable = [record.get(field, "") for field in KEYWORD_FIELDS]
        searchable.extend(record["ai_roles"])
        searchable.extend(outcome_text.get(key, []))
        if keyword and not any(keyword in field.casefold() for field in searchable):
            continue
        selected.append(record)

    selected_ids = {record["id"] for record in selected}
    history_ids = set()
    for record in selected:
        predecessor = record["supersedes"]
        while predecessor and predecessor not in selected_ids and predecessor not in history_ids:
            history_ids.add(predecessor)
            predecessor = records[predecessor]["supersedes"]

    def relative_paths(items):
        return [
            dict(item, **{key: item[key].relative_to(root).as_posix() for key in ("path", "image_path") if key in item})
            for item in items
        ]

    relevant_ids = selected_ids | history_ids
    return {
        "filters": filters,
        "selected": relative_paths(selected),
        "history": relative_paths([records[key] for key in sorted(history_ids, key=int)]),
        "events": relative_paths([event for event in events if event["record_id"] in relevant_ids]),
    }


def print_evidence(args, root, log):
    print(json.dumps(evidence_packet(args, root, log), ensure_ascii=False, indent=2))


def paragraph_text(value, name):
    if (not isinstance(value, str) or not value.strip() or len(value.splitlines()) != 1
            or value.lstrip().startswith(("#", ">", "- ", "* ", "---", "```", "[!["))):
        raise ValueError(f"{name} must be a single line of prose")
    return value.strip()


def validate_narrative(narrative, allowed_ids):
    if not isinstance(narrative, dict) or set(narrative) - {*NARRATIVE_SECTIONS, "themes"}:
        raise ValueError("Narrative keys must be overview, problem, constraints, or themes")

    def check_paragraphs(paragraphs):
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError("A narrative section must be a non-empty paragraph list")
        result = []
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict) or set(paragraph) != {"text", "sources"}:
                raise ValueError("Each narrative paragraph needs text and sources")
            prose = paragraph_text(paragraph["text"], "Paragraph text")
            sources = paragraph["sources"]
            if not isinstance(sources, list) or any(
                not isinstance(source, str) or source not in allowed_ids for source in sources
            ):
                raise ValueError("Paragraph sources must be confirmed IDs in the evidence packet")
            if not sources and not prose.startswith("[verify]"):
                raise ValueError("A paragraph without sources must begin with [verify]")
            result.append((prose, tuple(dict.fromkeys(sources))))
        return result

    result = {name: check_paragraphs(narrative[name]) for name in NARRATIVE_SECTIONS if name in narrative}
    if "themes" in narrative:
        themes = narrative["themes"]
        if not isinstance(themes, list) or not themes:
            raise ValueError("Themes must be a non-empty list")
        result["themes"] = []
        for theme in themes:
            if not isinstance(theme, dict) or set(theme) != {"title", "paragraphs"}:
                raise ValueError("Each theme needs a title and paragraphs")
            title = paragraph_text(theme["title"], "Theme title")
            result["themes"].append((title, check_paragraphs(theme["paragraphs"])))
    return result


def source_link(label, path, draft_dir):
    try:
        destination = Path(os.path.relpath(path, draft_dir)).as_posix()
    except ValueError:
        return f"[{label}]({path.as_uri()})"
    return f"[{label}]({quote(destination)})"


def sourced_field(text, link):
    """Keep the logged wording intact, including multiline lists."""
    if "\n" in text or text.startswith(("#", "- ", "* ", ">", "```")):
        quote_lines = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
        return f"{quote_lines}\n\n{link}"
    return f"{text} {link}"


def screenshot_line(event, root, draft_dir, receipt):
    label = {"before": "Before screenshot", "after": "After screenshot", "state": "UI state screenshot"}[event["state"]]
    image = source_link(label, root / event["image_path"], draft_dir)
    route, viewport, caption = [
        " ".join(event[field].split()).translate(MARKDOWN_ESCAPES)
        for field in ("route", "viewport", "text")
    ]
    return f"- {image} · {receipt} · {route} · {viewport} — {caption}"


def render_draft(packet, narrative, root, target):
    selected = packet["selected"]
    records = {record["id"]: record for record in (*selected, *packet["history"])}

    def receipt_link(record_id):
        return source_link(f"Receipt {record_id}", root / records[record_id]["path"], target.parent)

    def render_paragraphs(paragraphs):
        return [" ".join((prose, *(receipt_link(record_id) for record_id in ids))) for prose, ids in paragraphs]

    def source_blocks(field, subset=selected):
        return [sourced_field(record[field], receipt_link(record["id"])) for record in subset]

    overview = [
        "[verify] Add the project name, audience, and your role from project evidence.",
        f"The draft draws on {len(selected)} confirmed design {'decision' if len(selected) == 1 else 'decisions'}. "
        + " ".join(receipt_link(record["id"]) for record in selected),
    ]
    oldest = min(selected, key=lambda record: (record["date"], int(record["id"])))
    problem = source_blocks("context", [oldest])
    constraints = source_blocks("tradeoffs")
    decisions = []
    if "themes" in narrative:
        for title, paragraphs in narrative["themes"]:
            decisions.extend([f"### {title}", *render_paragraphs(paragraphs)])
    else:
        for record in selected:
            link = receipt_link(record["id"])
            decisions.extend([
                f"### {record['title']}",
                sourced_field(record["decision"], link),
                sourced_field(f"**Trade-off:** {record['tradeoffs']}", link),
            ])

    pivots = [records[key] for key in sorted(records, key=int) if records[key]["supersedes"]]
    if pivots:
        decisions.append("### How the decisions changed")
        for record in pivots:
            earlier_link = receipt_link(record["supersedes"])
            latest_link = receipt_link(record["id"])
            decisions.append(sourced_field(record["decision"], f"{latest_link} supersedes {earlier_link}."))
            decisions.append(sourced_field(record["context"], latest_link))

    ai = []
    outcomes = []
    reflection = []
    screenshots = []
    outcome_events = {}
    for event in packet["events"]:
        if event["kind"] == "outcome":
            outcome_events.setdefault(event["record_id"], []).append(event)
        elif event["kind"] == "screenshot":
            screenshots.append(screenshot_line(event, root, target.parent, receipt_link(event["record_id"])))
    for record in selected:
        link = receipt_link(record["id"])
        roles = record["ai_roles"]
        ai.append(f"**{record['title']}** · {', '.join(roles)}. {link}")
        if any(role.casefold() == "overruled by human" for role in roles):
            ai.append(sourced_field(f"**Human overrule.** {record['decision']}", link))
            ai.append(sourced_field(record["rejections"], link))

        observed = record.get("outcome", "").strip()
        if has_outcome(observed):
            outcomes.append(sourced_field(observed, link))
        elif record["id"] not in outcome_events:
            outcomes.append(f"[verify] No outcome recorded for **{record['title']}**. {link}")
        for event in outcome_events.get(record["id"], []):
            note = source_link(f"Outcome {event['date']}", root / event["path"], target.parent)
            outcomes.append(sourced_field(event["text"], f"{link} {note}"))

        questions = record.get("open_questions", "").strip()
        if questions and questions.casefold().rstrip(".") != "none":
            reflection.append(sourced_field(questions, link))
    for record in pivots:
        earlier = receipt_link(record["supersedes"])
        latest = receipt_link(record["id"])
        reflection.append(f"What changed your judgment between {earlier} and {latest}?")

    blocks = ["# Case study draft", "> Draft from confirmed decision receipts. Curate before sharing."]
    scope = [f"{key} `{value.replace('`', '')}`" for key, value in packet["filters"].items() if value]
    if scope:
        blocks.append("Selection · " + " · ".join(scope))
    sections = [
        ("Overview", render_paragraphs(narrative["overview"]) if "overview" in narrative else overview),
        ("Problem", render_paragraphs(narrative["problem"]) if "problem" in narrative else problem),
        ("Constraints", render_paragraphs(narrative["constraints"]) if "constraints" in narrative else constraints),
        ("Key decisions and trade-offs", decisions),
        ("What was avoided and why", source_blocks("rejections")),
        ("How AI was used", ai),
    ]
    if screenshots:
        sections.append(("Visual evidence", ["\n".join(screenshots)]))
    sections.extend([
        ("Outcomes", outcomes),
        ("Reflection", reflection or ["[verify] Add your reflection on what you would change next time."]),
    ])
    for title, body in sections:
        blocks.extend([f"## {title}", *body])
    return "\n\n".join(blocks) + "\n"


def target_path(root, log, output):
    drafts = log / "drafts"
    if output is None:
        if drafts.is_symlink():
            raise ValueError("The default drafts directory must be inside the decision log")
        return drafts / f"case-study-{date.today().isoformat()}.md"
    candidate = root / output
    if candidate.is_symlink():
        raise ValueError("Choose a draft path that is not a symbolic link")
    target = candidate.resolve()
    if target.is_relative_to(root) and any(part.casefold() == ".git" for part in target.relative_to(root).parts):
        raise ValueError("Choose a draft path outside Git metadata")
    if target.is_relative_to(log) and (
        drafts.is_symlink() or not target.is_relative_to(drafts) or target == drafts
    ):
        raise ValueError("Choose a path outside the decision log or inside its drafts directory")
    return target


def install_draft(target, text, overwrite, increment):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=target.parent)
    temporary_path = Path(name)
    try:
        with os.fdopen(fd, mode="w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary_path, target)
            return target
        suffix = 2
        candidate = target
        while True:
            try:
                os.link(temporary_path, candidate)
                return candidate
            except FileExistsError:
                if not increment:
                    raise ValueError(f"Draft already exists at {candidate}. Choose a new path or confirm replacement.") from None
                candidate = target.with_stem(f"{target.stem}-{suffix}")
                suffix += 1
    finally:
        temporary_path.unlink(missing_ok=True)


def compile_draft(args, root, log):
    if args.overwrite and args.output is None:
        raise ValueError("Specify --output to replace a draft")
    packet = evidence_packet(args, root, log)
    if not packet["selected"]:
        raise ValueError("No confirmed decisions match. Accept a receipt or widen the selection.")
    narrative = {}
    if args.narrative is not None:
        raw = sys.stdin.read() if args.narrative == "-" else (root / args.narrative).read_text(encoding="utf-8")
        allowed = {record["id"] for record in (*packet["selected"], *packet["history"])}
        narrative = validate_narrative(json.loads(raw), allowed)
    target = target_path(root, log, args.output)
    text = render_draft(packet, narrative, root, target)
    written = install_draft(target, text, args.overwrite, increment=args.output is None)
    print(written)
