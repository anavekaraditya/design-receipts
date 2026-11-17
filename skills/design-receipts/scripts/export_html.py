"""Render a curated Markdown draft and its linked evidence as portable HTML."""

import base64
import html
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

from receipt_log import SECTIONS, display_id, png_dimensions


INLINE = re.compile(
    r"\\([\\`*_{}\[\]()#+\-.!<>~&])"
    r"|`([^`\n]+)`"
    r"|(!?)\[([^\]\n]*)\]\(((?:[^()\n]|\([^()\n]*\))+)\)"
    r"|\*\*([^\n]+?)\*\*"
    r"|\*([^*\n]+)\*"
    r"|(?<!\w)_([^_\n]+)_(?!\w)"
    r"|<((?:https?://|mailto:)[^<>\s]+)>"
    r"|(\[verify\])",
    flags=re.IGNORECASE,
)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$")
LIST_ITEM = re.compile(r"^\s*(?:([-+*])|([0-9]+)[.)])\s+(.+)$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
TABLE_DIVIDER = re.compile(r"^:?-{3,}:?$")

STYLES = """
:root {
  color-scheme: light;
  --ink: #17253a;
  --secondary: #526078;
  --accent: #344bc2;
  --rule: #d3daea;
  --paper: #fdfdfb;
  --display-font: "Work Sans", sans-serif;
  --editorial-font: "Baskervville", serif;
}
* { box-sizing: border-box; }
html { font-size: 16px; }
body { margin: 0; color: var(--ink); background: var(--paper); font: 1rem/1.58 var(--display-font); font-kerning: normal; }
.report { max-width: 52rem; margin: 0 auto; padding: 3rem 3.5rem; }
h1, h2, h3, h4, h5, h6 { break-after: avoid; overflow-wrap: anywhere; font-weight: 600; }
h1 { font-size: 3rem; line-height: 1.08; letter-spacing: -0.05em; }
h2 { font-size: 1.8rem; line-height: 1.2; letter-spacing: -0.035em; margin: 2.5rem 0 1rem; }
h3 { font-size: 1.3rem; line-height: 1.35; letter-spacing: -0.025em; margin: 1.7rem 0 0.7rem; }
h4, h5, h6 { font-size: 0.9rem; line-height: 1.4; margin: 1.2rem 0 0.4rem; }
p { max-width: 64ch; margin: 0 0 1rem; orphans: 3; widows: 3; break-inside: avoid; overflow-wrap: anywhere; }
li { margin: 0.4rem 0; overflow-wrap: anywhere; }
ul, ol { max-width: 64ch; padding-left: 1.2rem; margin: 0 0 1.2rem; }
a { color: var(--accent); text-decoration-thickness: 0.5px; text-underline-offset: 0.18em; overflow-wrap: anywhere; }
a[href^="#receipt-"], a[href^="#event-"] { white-space: nowrap; }
strong { font-weight: 600; }
blockquote { max-width: 64ch; margin: 0 0 1.6rem; padding: 0.9rem 0; border-block: 0.5px solid var(--rule); color: var(--secondary); }
blockquote p { margin: 0; font-size: 0.9rem; }
code, pre { font-family: "Courier New", monospace; font-size: 0.88em; }
code { background: #edf0f8; padding: 0.1em 0.25em; }
pre { margin: 1.2rem 0; padding: 1rem; background: #edf0f8; white-space: pre-wrap; overflow-wrap: anywhere; }
pre code { padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1.5rem 0; table-layout: fixed; font-variant-numeric: tabular-nums; }
th, td { text-align: left; vertical-align: top; padding: 0.7rem 0.6rem; border-bottom: 0.5px solid var(--rule); overflow-wrap: anywhere; }
th { font-size: 0.75rem; font-weight: 600; color: var(--secondary); }
thead { display: table-header-group; }
tr { break-inside: avoid; }
mark { color: #754813; background: #fff0c9; padding: 0.05em 0.2em; }
.export-cover { position: relative; isolation: isolate; display: flex; flex-direction: column; min-height: 70rem; padding: 3rem; background: #4358d4; color: #fafcf5; }
.export-cover::before { content: ""; position: absolute; z-index: -1; inset: 1.4rem; border: 0.5px solid #ffffff35; background-image: linear-gradient(to right, #ffffff38 1px, transparent 1px), linear-gradient(to bottom, #ffffff38 1px, transparent 1px); background-size: 33.333% 100%, 100% 20%; }
.cover-top { display: flex; justify-content: space-between; align-items: baseline; gap: 2rem; }
.cover-brand { font-size: 0.8rem; letter-spacing: 0.09em; font-weight: 500; text-transform: uppercase; }
.cover-category { font-family: var(--editorial-font); font-size: 1.05rem; font-style: italic; }
.cover-title { display: flex; align-items: center; flex: 1; padding: 6rem 0; }
.cover-title h1 { max-width: 12ch; margin: 0; font-size: 4rem; font-weight: 400; line-height: 1.07; letter-spacing: -0.06em; text-wrap: balance; }
.cover-meta { display: grid; grid-template-columns: 1fr 2fr; border-top: 0.5px solid #ffffff60; padding-top: 1rem; gap: 2rem; font-variant-numeric: tabular-nums; }
.cover-meta p { margin: 0; font-size: 0.85rem; line-height: 1.5; }
.cover-meta span { display: block; margin-bottom: 0.5rem; font-size: 0.65rem; letter-spacing: 0.1em; text-transform: uppercase; opacity: 0.8; }
.captures { margin-top: 3rem; }
.captures > h2, .evidence > h2 { font: italic 2rem/1.25 var(--editorial-font); letter-spacing: -0.035em; margin: 0 0 1.8rem; }
figure { margin: 0 0 2rem; break-inside: avoid; }
figure img { display: block; width: 100%; height: auto; max-height: 38rem; object-fit: contain; object-position: left; border: 0.5px solid var(--rule); }
figcaption { color: var(--secondary); font-size: 0.8rem; line-height: 1.5; margin-top: 0.6rem; overflow-wrap: anywhere; }
figcaption strong { color: var(--ink); font-weight: 500; }
.source { margin: 2.5rem 0 0; }
.source-heading { margin-bottom: 1.7rem; padding-top: 0.8rem; border-top: 0.5px solid var(--rule); }
.source-heading h3 { margin: 0.6rem 0 0.8rem; font-size: 1.9rem; line-height: 1.15; font-weight: 500; letter-spacing: -0.04em; }
.source-number { font-size: 0.8rem; color: var(--accent); font-weight: 500; }
.metadata { color: var(--secondary); font-size: 0.8rem; line-height: 1.6; margin: 0; }
.source-field { margin: 0 0 1.4rem; }
.source-field h4 { font-size: 0.7rem; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; color: var(--secondary); margin: 0 0 0.45rem; }
.source-field p, .source-field ul, .source-field ol { margin-bottom: 0.7rem; }
.source-event { margin: 1.5rem 0; padding-top: 1rem; border-top: 0.5px solid var(--rule); }
.source-event h4 { font-size: 1rem; margin: 0 0 0.5rem; }
.source-event .metadata { margin-bottom: 0.8rem; }
.evidence { margin-top: 3rem; }
@page {
  size: A4;
  margin: 19mm 22mm 22mm;
  @bottom-left { content: "Design Receipts"; font: 8pt "Work Sans", sans-serif; letter-spacing: 0.03em; color: #68738a; vertical-align: top; padding-top: 5mm; border-top: 0.5px solid #d3daea; }
  @bottom-right { content: counter(page) " / " counter(pages); font: 8pt "Work Sans", sans-serif; color: #68738a; vertical-align: top; padding-top: 5mm; border-top: 0.5px solid #d3daea; }
}
@page cover { margin: 0; @bottom-left { content: none; } @bottom-right { content: none; } }
@media print {
  body { font-size: 11.5pt; line-height: 1.53; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  .export-cover { page: cover; height: 297mm; min-height: 0; padding: 20mm 22mm; break-after: page; }
  .export-cover::before { inset: 10mm; }
  .cover-brand { font-size: 9pt; }
  .cover-category { font-size: 13pt; }
  .cover-title { padding: 20mm 0; }
  .cover-title h1 { font-size: 47pt; max-width: 13ch; }
  .cover-meta { gap: 12mm; padding-top: 6mm; }
  .cover-meta p { font-size: 10pt; }
  .cover-meta span { font-size: 8pt; }
  .report { page: report; max-width: none; padding: 0; }
  h2 { font-size: 22pt; margin: 7mm 0 3.5mm; }
  h3 { font-size: 14.5pt; margin: 5mm 0 3mm; }
  p { margin-bottom: 3.5mm; }
  ul, ol { margin-bottom: 5mm; }
  li { margin: 2mm 0; }
  blockquote { margin-bottom: 6mm; padding: 3mm 0; }
  blockquote p { font-size: 9.5pt; }
  .captures { break-before: page; margin: 0; }
  .captures > h2, .evidence > h2 { font-size: 28pt; margin: 0 0 8mm; }
  figure { margin-bottom: 8mm; }
  figure img { max-height: 177mm; }
  figcaption { font-size: 9.5pt; margin-top: 3mm; }
  .source { margin-top: 0; }
  .source + .source { break-before: page; }
  .source-heading { margin-bottom: 8mm; padding-top: 4mm; }
  .source-heading h3 { font-size: 23pt; margin: 3mm 0 4mm; }
  .source-number, .metadata { font-size: 9.5pt; }
  .source-field { margin-bottom: 6mm; }
  .source-field h4 { font-size: 8.5pt; margin-bottom: 2mm; }
  .source-event { margin: 7mm 0; padding-top: 5mm; }
  .source-event h4 { font-size: 12.5pt; }
  .evidence { margin-top: 0; }
  .evidence { break-before: page; }
}
"""


def font_styles():
    directory = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    faces = (
        ("Work Sans", "work-sans.ttf", "normal", "400"),
        ("Work Sans", "work-sans-medium.ttf", "normal", "500"),
        ("Work Sans", "work-sans-semibold.ttf", "normal", "600"),
        ("Baskervville", "baskervville-italic.ttf", "italic", "400"),
    )
    rules = []
    for family, filename, style, weight in faces:
        encoded = base64.b64encode((directory / filename).read_bytes()).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{family}"; font-style: {style}; font-weight: {weight}; '
            f'src: url(data:font/ttf;base64,{encoded}) format("truetype"); }}'
        )
    return "\n".join(rules)


def escape(value):
    return html.escape(str(value), quote=True)


def table_cells(line):
    line = line.strip().strip("|")
    return re.split(r"(?<!\\)\|", line)


def heading_anchor(text):
    return re.sub(r"[^\w-]+", "-", text.casefold()).strip("-") or "section"


class ExportDocument:
    def __init__(self, source_path, records, events):
        self.source_path = Path(source_path).resolve()
        self.records = {key: value for key, value in records.items() if value["status"] == "accepted"}
        self.events = {event["id"]: event for event in events if event["record_id"] in self.records}
        self.references = {record["path"].resolve(): ("record", record["id"]) for record in self.records.values()}
        for event in self.events.values():
            self.references[event["path"].resolve()] = ("event", event["id"])
            if event["kind"] == "screenshot":
                self.references[event["image_path"].resolve()] = ("screenshot", event["id"])
        self.used_records = set()
        self.used_events = set()
        self.used_images = set()
        self.heading_counts = {}

    def link(self, label, destination, *, evidence=False):
        destination = destination.strip()
        titled = re.fullmatch(r'''(<[^>\n]+>|\S+)\s+(?:"[^"\n]*"|'[^'\n]*')''', destination)
        if titled:
            destination = titled[1]
        if destination.startswith("<") and destination.endswith(">"):
            destination = destination[1:-1]
        url = urlsplit(destination)
        if url.scheme.casefold() in ("http", "https", "mailto"):
            return f'<a href="{escape(destination)}" rel="noreferrer">{label}</a>'
        if url.scheme and url.scheme != "file":
            return label
        if not url.path and url.fragment:
            return f'<a href="#section-{escape(heading_anchor(unquote(url.fragment)))}">{label}</a>'
        if evidence:
            return label
        if url.netloc or url.query:
            raise ValueError(f"Export cannot include local evidence link {destination!r}. Use a decision or attached screenshot link.")
        target = (self.source_path.parent / unquote(url.path)).resolve()
        if target == self.source_path and url.fragment:
            return f'<a href="#section-{escape(heading_anchor(unquote(url.fragment)))}">{label}</a>'
        reference = self.references.get(target)
        if reference is None:
            raise ValueError(f"Export cannot resolve {destination!r}. Link an accepted decision, dated event, or attached screenshot.")
        kind, identifier = reference
        if kind == "record":
            self.used_records.add(identifier)
            anchor = f"receipt-{identifier}"
            number = re.fullmatch(r"(?:Receipt|Decision) +([0-9]+)", label, flags=re.IGNORECASE)
            if number and int(number[1]) == int(identifier):
                label = f"Decision {display_id(identifier)}"
        else:
            event = self.events[identifier]
            self.used_records.add(event["record_id"])
            self.used_events.add(identifier)
            if kind == "screenshot" or event["kind"] == "screenshot":
                self.used_images.add(identifier)
                anchor = f"capture-{identifier}"
            else:
                anchor = f"event-{identifier}"
        return f'<a href="#{anchor}">{label}</a>'

    def inline(self, text, *, evidence=False, depth=0):
        if depth > 8:
            return escape(text)
        parts = []
        position = 0
        for token in INLINE.finditer(text):
            parts.append(escape(text[position:token.start()]))
            escaped, code, image, label, destination, strong, emphasis, underscore, autolink, verify = token.groups()
            if escaped is not None:
                parts.append(escape(escaped))
            elif code is not None:
                parts.append(f"<code>{escape(code)}</code>")
            elif destination is not None:
                rendered_label = self.inline(label, evidence=evidence, depth=depth + 1)
                parts.append(self.link(rendered_label, destination, evidence=evidence))
            elif strong is not None:
                parts.append(f"<strong>{self.inline(strong, evidence=evidence, depth=depth + 1)}</strong>")
            elif emphasis is not None or underscore is not None:
                content = emphasis if emphasis is not None else underscore
                parts.append(f"<em>{self.inline(content, evidence=evidence, depth=depth + 1)}</em>")
            elif autolink is not None:
                parts.append(self.link(escape(autolink), autolink, evidence=evidence))
            elif verify is not None:
                parts.append(f"<mark>{escape(verify)}</mark>")
            position = token.end()
        parts.append(escape(text[position:]))
        return "".join(parts)

    def heading(self, level, text, *, evidence=False):
        slug = heading_anchor(text)
        count = self.heading_counts.get(slug, 0) + 1
        self.heading_counts[slug] = count
        suffix = f"-{count}" if count > 1 else ""
        return f'<h{level} id="section-{escape(slug + suffix)}">{self.inline(text, evidence=evidence)}</h{level}>'

    def markdown(self, source, *, evidence=False):
        lines = source.splitlines()
        rendered = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue
            fence = FENCE.match(line)
            if fence:
                marker = fence[1]
                code = []
                index += 1
                while index < len(lines) and not re.fullmatch(rf"\s*{re.escape(marker[0])}{{{len(marker)},}}\s*", lines[index]):
                    code.append(lines[index])
                    index += 1
                rendered.append(f"<pre><code>{escape(chr(10).join(code))}</code></pre>")
                index += 1
                continue
            heading = HEADING.match(line)
            if heading:
                rendered.append(self.heading(len(heading[1]), heading[2], evidence=evidence))
                index += 1
                continue
            if line.lstrip().startswith(">"):
                quoted = []
                while index < len(lines) and lines[index].lstrip().startswith(">"):
                    quoted.append(re.sub(r"^\s*> ?", "", lines[index]))
                    index += 1
                rendered.append(f"<blockquote>{self.markdown(chr(10).join(quoted), evidence=evidence)}</blockquote>")
                continue
            if index + 1 < len(lines) and "|" in line:
                dividers = table_cells(lines[index + 1])
                if dividers and all(TABLE_DIVIDER.fullmatch(cell.strip()) for cell in dividers):
                    rows = [table_cells(line)]
                    index += 2
                    while index < len(lines) and "|" in lines[index] and lines[index].strip():
                        rows.append(table_cells(lines[index]))
                        index += 1
                    headings = "".join(f'<th scope="col">{self.inline(cell.strip(), evidence=evidence)}</th>' for cell in rows[0])
                    body = "".join("<tr>" + "".join(f"<td>{self.inline(cell.strip(), evidence=evidence)}</td>" for cell in row) + "</tr>" for row in rows[1:])
                    rendered.append(f"<table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table>")
                    continue
            item = LIST_ITEM.match(line)
            if item:
                ordered = item[2] is not None
                tag = "ol" if ordered else "ul"
                start = f' start="{item[2]}"' if ordered and item[2] != "1" else ""
                items = []
                while index < len(lines):
                    item = LIST_ITEM.match(lines[index])
                    if not item or (item[2] is not None) != ordered:
                        break
                    items.append(f"<li>{self.inline(item[3], evidence=evidence)}</li>")
                    index += 1
                rendered.append(f"<{tag}{start}>{''.join(items)}</{tag}>")
                continue
            paragraph = [line]
            index += 1
            while index < len(lines) and lines[index].strip():
                candidate = lines[index]
                if HEADING.match(candidate) or FENCE.match(candidate) or LIST_ITEM.match(candidate) or candidate.lstrip().startswith(">"):
                    break
                paragraph.append(candidate)
                index += 1
            rendered.append(f"<p>{self.inline(chr(10).join(paragraph), evidence=evidence)}</p>")
        return "\n".join(rendered)

    def screenshots(self):
        figures = []
        for identifier in sorted(self.used_images, key=int):
            event = self.events[identifier]
            image = event["image_path"]
            png_dimensions(image)
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
            description = f"{event['state'].capitalize()} · {event['route']} · {event['viewport']} · {event['date']}"
            caption = escape(event["text"])
            record_id = event["record_id"]
            figures.append(
                f'<figure id="capture-{identifier}"><img src="data:image/png;base64,{encoded}" alt="{caption}">'
                f'<figcaption><strong>{caption}</strong><br>{escape(description)} · '
                f'<a href="#receipt-{record_id}">Decision {display_id(record_id)}</a></figcaption></figure>'
            )
        if not figures:
            return ""
        return '<section class="captures" aria-label="Captured states"><h2>Captured states</h2>' + "\n".join(figures) + "</section>"

    def cover(self, heading):
        metadata = ""
        if self.used_records:
            days = sorted(date.fromisoformat(self.records[key]["date"]) for key in self.used_records)
            span = " - ".join(f"{day.day} {day.strftime('%b %Y')}" for day in dict.fromkeys((days[0], days[-1])))
            metadata = (
                '<div class="cover-meta">'
                f'<p><span>Decisions documented</span>{len(self.used_records)}</p>'
                f'<p><span>Decision span</span>{escape(span)}</p></div>'
            )
        return (
            '<header class="export-cover"><div class="cover-top">'
            '<span class="cover-brand">Design Receipts</span>'
            '<span class="cover-category">Project documentation</span></div>'
            f'<div class="cover-title">{heading}</div>{metadata}</header>'
        )

    def appendix(self):
        sources = []
        for identifier in sorted(self.used_records, key=int):
            record = self.records[identifier]
            fields = []
            for field, heading in SECTIONS.items():
                if record.get(field):
                    fields.append(
                        '<div class="source-field">'
                        f"<h4>{escape(heading)}</h4>{self.markdown(record[field], evidence=True)}</div>"
                    )
            metadata = f"{record['date']} · {record['effective_status']} · {', '.join(record['ai_roles'])}"
            if record.get("supersedes"):
                metadata += f" · Supersedes Decision {display_id(record['supersedes'])}"
            linked_events = []
            for event_id in sorted(self.used_events, key=int):
                event = self.events[event_id]
                if event["record_id"] != identifier or event["kind"] == "screenshot":
                    continue
                linked_events.append(
                    f'<section class="source-event" id="event-{event_id}">'
                    f'<h4>{escape(event["kind"].capitalize())} {event["date"]}</h4>'
                    f'<p class="metadata"><a href="#receipt-{identifier}">Decision {display_id(identifier)}</a></p>'
                    f'{self.markdown(event["text"], evidence=True)}</section>'
                )
            sources.append(
                f'<article class="source" id="receipt-{identifier}"><header class="source-heading">'
                f'<span class="source-number">Decision {display_id(identifier)}</span>'
                f'<h3>{escape(record["title"])}</h3><p class="metadata">{escape(metadata)}</p></header>'
                f'{chr(10).join(fields)}{chr(10).join(linked_events)}</article>'
            )
        if not sources:
            return ""
        return '<section class="evidence" aria-label="Source evidence"><h2>Source evidence</h2>' + "\n".join(sources) + "</section>"


def render_export(source, source_path, records, events, title=None):
    """Preserve the edited draft and embed only the evidence its links reference."""
    document = ExportDocument(source_path, records, events)
    first_heading = next((line[2:] for line in source.splitlines() if line.startswith("# ")), None)
    document_title = title or first_heading or "Design Receipts"
    body = document.markdown(source)
    heading = re.search(r"<h1\b[^>]*>.*?</h1>", body)
    if heading:
        cover_heading = heading[0]
        body = body[:heading.start()] + body[heading.end():]
    else:
        cover_heading = f"<h1>{escape(document_title)}</h1>"
    cover = document.cover(cover_heading)
    screenshots = document.screenshots()
    appendix = document.appendix()
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; font-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        f"<title>{escape(document_title)}</title><style>{font_styles()}\n{STYLES}</style></head>"
        f'<body>{cover}<main class="report">{body}\n{screenshots}\n{appendix}</main></body></html>\n'
    )
