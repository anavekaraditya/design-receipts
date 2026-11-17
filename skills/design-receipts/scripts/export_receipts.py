"""Export an edited Markdown draft as a portable PDF with its linked evidence."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from compile_receipts import install_draft, target_path
from export_html import render_export
from receipt_log import read_log, read_managed_text


PRINTER = Path(__file__).with_name("print_export.cjs")


def add_export_command(subparsers):
    command = subparsers.add_parser("export", help="export an edited Markdown draft to PDF")
    command.add_argument("draft", type=Path, help="Markdown draft relative to the project, or absolute")
    command.add_argument("--output", type=Path, help="PDF path relative to the project, or absolute")
    command.add_argument("--overwrite", action="store_true", help="replace this PDF after designer confirmation")
    command.add_argument("--playwright-module", type=Path, help="absolute path to an installed Playwright package")
    command.add_argument("--browser-executable", type=Path, help="path to an installed compatible Chromium")
    command.set_defaults(handler=export_pdf)


def print_pdf(html, workspace, root, args):
    node = shutil.which("node")
    if node is None:
        raise ValueError("PDF export needs Node.js 18+ and an installed Playwright browser. See references/export.md.")
    document = workspace / "document.html"
    pdf = workspace / "document.pdf"
    document.write_text(html, encoding="utf-8")
    command = [node, str(PRINTER), "--input", str(document), "--output", str(pdf)]
    if args.playwright_module:
        command.extend(["--module", str(args.playwright_module)])
    if args.browser_executable:
        command.extend(["--browser-executable", str((root / args.browser_executable).resolve())])
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise ValueError("PDF rendering timed out. The draft and previous export are intact.") from None
    if result.returncode:
        reason = (result.stderr.strip() or "The browser could not render the PDF.").splitlines()[0]
        raise ValueError(f"{reason} See references/export.md for PDF browser setup.")
    if not pdf.is_file():
        raise ValueError("The browser returned without writing a PDF. The draft is intact.")
    content = pdf.read_bytes()
    if not content.startswith(b"%PDF-") or not content.rstrip().endswith(b"%%EOF"):
        raise ValueError("The browser did not produce a complete PDF. The draft is intact.")
    return content


def export_pdf(args, root, log):
    if args.overwrite and args.output is None:
        raise ValueError("Specify --output to replace an exported PDF")
    source = root / args.draft
    if source.suffix.casefold() != ".md":
        raise ValueError("Choose the Markdown draft (.md) you want to export")
    content = read_managed_text(source)
    if not content.strip():
        raise ValueError("The draft is empty. Compile or write a draft before exporting it.")
    source = source.resolve()
    output = args.output if args.output is not None else log / "drafts" / f"{source.stem}.pdf"
    target = target_path(root, log, str(output))
    if target == source or target.suffix.casefold() != ".pdf":
        raise ValueError("Choose a .pdf output path separate from the Markdown draft")
    if target.exists() and args.output is not None and not args.overwrite:
        raise ValueError(f"PDF already exists at {target}. Choose a new path or confirm replacement.")

    records, events = read_log(log)
    html = render_export(content, source, records, events)
    with tempfile.TemporaryDirectory(prefix="design-receipts-export-") as directory:
        document = print_pdf(html, Path(directory), root, args)
    written = install_draft(target, document, args.overwrite, increment=args.output is None)
    print(written)
