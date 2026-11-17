import base64
import re
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "design-receipts" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from export_html import render_export


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X0ZkAAAAASUVORK5CYII=")


class ExportHtmlTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.log = self.root / "research notes"
        self.log.mkdir()
        self.source = self.log / "drafts" / "edited.md"
        self.source.parent.mkdir()
        self.records = {
            "0001": self.record("0001"),
            "0002": self.record("0002", status="proposed"),
            "0003": self.record("0003"),
        }
        bundle = self.log / "events" / "0001-screenshot-0001"
        bundle.mkdir(parents=True)
        image = bundle / "image.png"
        image.write_bytes(PNG)
        self.events = [{
            "id": "0001", "kind": "screenshot", "record_id": "0001", "date": "2026-11-17",
            "path": bundle / "README.md", "image_path": image, "route": "/stops", "viewport": "1440x900",
            "state": "after", "text": "Selected stop <open> & arrival visible",
        }, {
            "id": "0002", "kind": "outcome", "record_id": "0001", "date": "2026-11-18",
            "path": self.log / "events" / "0002-outcome-0001.md", "text": "The designer checked the expanded state.",
        }]

    def record(self, identifier, status="accepted"):
        return {
            "id": identifier, "title": f"Decision {identifier}", "path": self.log / f"{identifier}-choice.md",
            "date": "2026-11-16", "status": status, "effective_status": status, "supersedes": None,
            "ai_roles": ["Decided by human"], "context": "Route names need room.",
            "decision": "Reveal arrivals on tap.", "options": "- Chosen: Reveal on tap\n- Alternative: Show all",
            "rejections": "Showing all arrivals crowds the list.", "tradeoffs": "Riders tap once more.",
            "outcome": "", "open_questions": "", "evidence": "",
        }

    def render(self, source, **kwargs):
        return render_export(source, self.source, self.records, self.events, **kwargs)

    def test_embeds_only_linked_evidence_and_retains_edited_words(self):
        draft = """# My edited case study

I chose this because the original list felt crowded. [Receipt 0001](../0001-choice.md)

## Visual evidence

- [After screenshot](../events/0001-screenshot-0001/image.png) · /stops · 1440x900 — The arrival is expanded.

## Outcomes

[verify] Measure scanning time later.
"""
        output = self.render(draft)
        self.assertIn("I chose this because the original list felt crowded.", output)
        self.assertIn('href="#receipt-0001"', output)
        self.assertIn('id="receipt-0001"', output)
        self.assertIn('href="#receipt-0001">Decision 1</a>', output)
        self.assertIn('<span class="source-number">Decision 1</span>', output)
        self.assertIn('<h3>Decision 0001</h3>', output)
        self.assertNotIn('>Receipt 0001</a>', output)
        self.assertIn('href="#capture-0001"', output)
        self.assertIn(f'src="data:image/png;base64,{base64.b64encode(PNG).decode()}"', output)
        self.assertIn("Selected stop &lt;open&gt; &amp; arrival visible", output)
        self.assertIn("After · /stops · 1440x900 · 2026-11-17", output)
        self.assertIn("<mark>[verify]</mark> Measure scanning time later.", output)
        self.assertNotIn("Decision 0002", output)
        self.assertNotIn("Decision 0003", output)
        self.assertNotIn("The designer checked", output)
        self.assertNotIn(str(self.root), output)

    def test_relative_encoded_links_and_outcome_citations_work(self):
        source = self.root / "portfolio.md"
        output = render_export(
            "[Receipt](research%20notes/0001-choice.md)\n\n"
            "[Outcome](research%20notes/events/0002-outcome-0001.md)",
            source, self.records, self.events,
        )
        self.assertIn('href="#receipt-0001"', output)
        self.assertIn('href="#event-0002"', output)
        self.assertIn('id="event-0002"', output)
        self.assertIn("The designer checked the expanded state.", output)
        self.assertNotIn("Captured states", output)

    def test_screenshot_metadata_link_embeds_the_same_image_once(self):
        output = self.render(
            "[Captured state](../events/0001-screenshot-0001/README.md)\n\n"
            "![After](../events/0001-screenshot-0001/image.png)"
        )
        self.assertEqual(output.count('src="data:image/png;base64,'), 1)
        self.assertEqual(output.count('href="#capture-0001"'), 2)
        self.assertIn('id="receipt-0001"', output)
        self.assertNotIn('href="../', output)

    def test_renders_markdown_and_raw_html_stays_inert(self):
        output = self.render("""# Test <script>alert('x')</script>

**Bold** and *emphasis* with `code` and [a source](https://example.invalid/?a=1&b=2).

> A quoted field with [verify].

1. First step
2. Second step

| Choice | Cost |
| --- | --- |
| Tap | One step |

```html
<img src="https://example.invalid/track" onerror="alert('x')">
```

<iframe src="https://example.invalid"></iframe>

[Unsafe](javascript:alert) and [Data](data:text/html,test)
""")
        self.assertIn("<strong>Bold</strong>", output)
        self.assertIn("<em>emphasis</em>", output)
        self.assertIn("<code>code</code>", output)
        self.assertIn("<blockquote>", output)
        self.assertIn("<ol>", output)
        self.assertIn("<table>", output)
        self.assertIn("<pre><code>&lt;img", output)
        self.assertIn("&lt;iframe", output)
        self.assertNotIn("<script>", output)
        self.assertNotIn("<iframe", output)
        self.assertNotIn('href="javascript:', output)
        self.assertNotIn('href="data:', output)
        self.assertIn('href="https://example.invalid/?a=1&amp;b=2"', output)
        self.assertEqual(re.findall(r'<(?:img|script|iframe)\b', output), [])

    def test_rejects_missing_or_undeclared_assets_and_proposed_receipts(self):
        for destination in ("../0002-choice.md", "../../secrets.txt", "../events/missing.png"):
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "Export cannot resolve"):
                self.render(f"[Evidence]({destination})")
        self.events[0]["image_path"].unlink()
        with self.assertRaisesRegex(ValueError, "regular PNG"):
            self.render("![After](../events/0001-screenshot-0001/image.png)")

    def test_evidence_fields_do_not_recursively_export_unrelated_records(self):
        self.records["0001"]["evidence"] = "See [other receipt](0003-choice.md) and [Figma](https://figma.com/file/test)."
        output = self.render("[Receipt](../0001-choice.md)")
        self.assertIn("See other receipt", output)
        self.assertIn('href="https://figma.com/file/test"', output)
        self.assertNotIn("Decision 0003", output)
        self.assertNotIn("receipt-0003", output)

    def test_decision_labels_preserve_legacy_targets_and_custom_wording(self):
        self.records["0003"]["supersedes"] = "0001"
        output = self.render(
            "[Receipt 0001](../0001-choice.md) and [Decision 0001](../0001-choice.md) "
            "and [Decision 1](../0001-choice.md).\n\n"
            "[My initial choice](../0001-choice.md) and [Receipt](../0001-choice.md).\n\n"
            "[Decision 3](../0003-choice.md).\n\n"
            "The designer called the earlier prototype Receipt 0001."
        )
        self.assertEqual(output.count('href="#receipt-0001">Decision 1</a>'), 3)
        self.assertIn('href="#receipt-0001">My initial choice</a>', output)
        self.assertIn('href="#receipt-0001">Receipt</a>', output)
        self.assertIn('href="#receipt-0003">Decision 3</a>', output)
        self.assertIn("Supersedes Decision 1", output)
        self.assertIn("The designer called the earlier prototype Receipt 0001.", output)

    def test_source_headings_and_encoded_fragments_do_not_collide_with_evidence(self):
        output = self.render(
            "# My case study\n\n"
            "[Jump to my section](#receipt-0001) and [Décision](#d%C3%A9cision).\n\n"
            "[Same draft](edited.md#d%C3%A9cision)\n\n"
            "## Receipt 0001\n\n"
            "[Source evidence](../0001-choice.md)\n\n"
            "## Décision\n\n"
            "My edited observation.\n"
        )
        ids = re.findall(r'\bid="([^"]+)"', output)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('id="section-receipt-0001"', output)
        self.assertIn('id="receipt-0001"', output)
        self.assertIn('href="#section-receipt-0001"', output)
        self.assertIn('id="section-décision"', output)
        self.assertEqual(output.count('href="#section-décision"'), 2)

    def test_inline_links_allow_titles_and_balanced_url_parentheses(self):
        output = self.render(
            '[Read](https://example.invalid/Design_(process) "Further reading")\n\n'
            '[Receipt](../0001-choice.md "Original choice")'
        )
        self.assertIn('href="https://example.invalid/Design_(process)"', output)
        self.assertIn('href="#receipt-0001"', output)
        self.assertNotIn('process)</a>)', output)


if __name__ == "__main__":
    unittest.main()
