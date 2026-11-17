# Export a PDF

Export the designer's current Markdown draft with the `export` command. It preserves the draft's wording and headings, embeds its linked screenshots, and turns decision citations into links to an evidence appendix within the PDF. Only evidence linked from the draft is included.

```sh
python3 -SB <skill-directory>/scripts/receipts.py export docs/decisions/drafts/case-study-2026-11-17.md
```

The default output is a new PDF in the log's `drafts/` directory, using the Markdown file's base name. Repeated exports receive a numeric suffix. Use `--output PATH` for a requested destination. Use `--overwrite` only after the designer confirms replacing that exact PDF. The Markdown draft and decision log are preserved.

The default design uses a blue cover with a fine grid, Work Sans body text, and Baskervville Italic section titles. The A4 interior has 11.5-point body text, generous margins, captioned screenshots, and numbered pages. Each decision's source evidence starts on a fresh page with its linked outcomes. Both typefaces and their open-font licenses are bundled for consistent offline export.

Export supports the compiler's headings, paragraphs, lists, quotes, tables, code blocks, and inline links. Use `[label](path)` links for decision citations and screenshot attachments in an edited draft.

When a designer asks to export their documentation, use the existing draft they named. If no draft exists, follow the [compile workflow](compile.md) to create it before exporting. Keep any `[verify]` gaps visible for their review. To export a slice of the project, compile that selection and export the resulting draft.

## Local PDF renderer

PDF printing uses Node.js 18+, an installed Playwright package, and Chromium. Use the project's existing browser setup or the host's bundled packages. The helper resolves Playwright from the project by default. If the package or browser lives elsewhere, pass its installed path.

```sh
python3 -SB <skill-directory>/scripts/receipts.py export docs/decisions/drafts/case-study-2026-11-17.md \
  --playwright-module /absolute/path/to/playwright \
  --browser-executable /absolute/path/to/chromium
```

The renderer uses a fresh offline browser context. Screenshots are embedded locally. External evidence URLs remain clickable links. If the runtime is unavailable, report the missing dependency and retain the Markdown draft. If a referenced local image or decision record is missing, resolve that link before retrying the export.

Open the completed PDF and check the title, headings, page breaks, and screenshot captions. Confirm that all screenshots are legible and the decision links lead to the appendix. Show the file link and any consequential evidence gaps. Review both text and images before sharing an export outside the project.
