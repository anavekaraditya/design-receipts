import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "design-receipts" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import compile_receipts


class CompileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.log = self.root / "docs" / "decisions"
        self.log.mkdir(parents=True)
        self.parser = argparse.ArgumentParser()
        compile_receipts.add_commands(self.parser.add_subparsers(required=True))
        self.records = {
            "0001": self.record(
                "0001", "Group arrivals", "2026-10-01", effective_status="superseded",
                decision="Group arrivals by route.", rejections="Rejected clock time because related arrivals split up.",
                ai_roles=["Proposed by AI", "Overruled by human"],
            ),
            "0002": self.record(
                "0002", "Show next arrival first", "2026-11-16", supersedes="0001",
                context="Riders wanted the next bus first, regardless of route.",
                decision="Sort upcoming buses by time and label every route.",
                rejections="Keep route groups as the default.\nThe next bus would be buried.",
                ai_roles=["Built by AI", "Overruled by human"],
                outcome="To be observed — run the test next Tuesday.",
                open_questions="When is a route filter more useful than a sort?",
            ),
            "0003": self.record(
                "0003", "Add future search", "2026-11-16", status="proposed", effective_status="proposed",
                decision="Unconfirmed idea: add future search.",
            ),
            "0004": self.record(
                "0004", "Use a map pin", "2026-10-05", effective_status="deprecated",
                outcome="The pin covered two neighboring stops.",
            ),
        }
        outcome_note = self.log / "events" / "0001-outcome-0002.md"
        self.events = [{
            "kind": "outcome", "record_id": "0002", "date": "2026-11-18",
            "text": "In the hallway test, two riders read the stop sign first.", "path": outcome_note,
        }]
        read_log = patch.object(compile_receipts, "read_log", return_value=(self.records, self.events))
        read_log.start()
        self.addCleanup(read_log.stop)

    def record(self, record_id, title, date, **overrides):
        return {
            "id": record_id, "title": title, "date": date, "status": "accepted", "effective_status": "accepted",
            "supersedes": None, "path": self.log / f"{record_id}-route.md", "context": "A rider needs a bus.",
            "decision": "Show a bus.", "options": "List or map.", "rejections": "Map hides the time.",
            "tradeoffs": "Less spatial context.", "outcome": "", "open_questions": "", "evidence": "",
            "ai_roles": ["Decided by human"],
            **overrides,
        }

    def run_action(self, *arguments, stdin=""):
        if arguments and arguments[0] == "compile" and "--edition" not in arguments:
            arguments = (*arguments, "--edition", "archive")
        args = self.parser.parse_args(arguments)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(sys, "stdin", io.StringIO(stdin)):
            args.handler(args, self.root, self.log)
        return output.getvalue().strip()

    def screenshot(self, record_id, state, caption):
        path = self.log / "screenshots" / f"{record_id} {state}" / "README.md"
        path.parent.mkdir(parents=True)
        path.write_text(caption, encoding="utf-8")
        image = path.with_name("screen.png")
        image.touch()
        self.events.append({
            "id": f"{len(self.events) + 1:04d}", "kind": "screenshot", "record_id": record_id,
            "date": "2026-11-18", "text": caption, "path": path, "image_path": image,
            "route": "/arrivals", "state": state, "viewport": "1440x900",
        })
        return image

    def test_full_draft_uses_confirmed_evidence_and_surfaces_each_overrule(self):
        output = Path(self.run_action("compile"))
        self.assertEqual(output.parent, self.log / "drafts")
        draft = output.read_text(encoding="utf-8")
        self.assertNotIn("Unconfirmed idea", draft)
        self.assertEqual(draft.count("**Human overrule.**"), 2)
        self.assertIn("Rejected clock time because related arrivals split up. [Decision 1]", draft)
        self.assertIn("> The next bus would be buried.", draft)
        self.assertIn("[verify] No outcome recorded for **Group arrivals**", draft)
        self.assertIn("The pin covered two neighboring stops. [Decision 4]", draft)
        self.assertIn("[Outcome 2026-11-18](../events/0001-outcome-0002.md)", draft)
        self.assertNotIn("run the test next Tuesday", draft)
        self.assertNotIn("No outcome recorded for **Show next arrival first**", draft)
        self.assertIn("When is a route filter more useful than a sort? [Decision 2]", draft)
        self.assertNotIn("## Visual evidence", draft)

    def test_combines_filters_and_includes_older_history(self):
        filters = ("--from", "2026-11-16", "--to", "2026-11-16", "--status", "accepted", "--keyword", "HALLWAY TEST")
        packet = json.loads(self.run_action("evidence", *filters))
        self.assertEqual([record["id"] for record in packet["selected"]], ["0002"])
        self.assertEqual([record["id"] for record in packet["history"]], ["0001"])
        self.assertEqual(packet["events"][0]["record_id"], "0002")
        self.assertEqual(packet["selected"][0]["path"], "docs/decisions/0002-route.md")
        draft = Path(self.run_action("compile", *filters)).read_text(encoding="utf-8")
        self.assertIn("[Decision 2](../0002-route.md) supersedes [Decision 1](../0001-route.md)", draft)
        self.assertIn("When is a route filter more useful than a sort?", draft)
        self.assertIn("keyword `HALLWAY TEST`", draft)
        self.assertEqual(draft.count("**Human overrule.**"), 1)

    def test_screenshots_follow_selected_receipts_and_history(self):
        self.events.clear()
        before = self.screenshot("0001", "before", "Grouped arrivals on the earlier list")
        after = self.screenshot("0002", "after", "The next arrival above the route labels")
        self.screenshot("0003", "state", "Unconfirmed search panel")
        self.screenshot("0004", "state", "The filtered map pin")
        filters = ("--status", "accepted", "--from", "2026-11-16")
        packet = json.loads(self.run_action("evidence", *filters))
        self.assertEqual([event["record_id"] for event in packet["events"]], ["0001", "0002"])
        self.assertEqual(
            [event["image_path"] for event in packet["events"]],
            [image.relative_to(self.root).as_posix() for image in (before, after)],
        )
        output = Path(self.run_action("compile", *filters, "--output", "portfolio/draft.md"))
        draft = output.read_text(encoding="utf-8")
        self.assertNotIn("Unconfirmed search panel", draft)
        self.assertNotIn("The filtered map pin", draft)
        visuals, outcomes_and_reflection = draft.split("## Visual evidence\n\n", 1)[1].split("## Outcomes\n\n", 1)
        self.assertIn("[Decision 2](../docs/decisions/0002-route.md) · /arrivals · 1440x900", visuals)
        links = re.findall(r"\[(?:Before|After) screenshot\]\(([^)]+)\)", visuals)
        self.assertEqual([(output.parent / unquote(link)).resolve(strict=True) for link in links], [before, after])
        self.assertIn("[verify] No outcome recorded", outcomes_and_reflection)
        self.assertNotIn("The next arrival above the route labels", outcomes_and_reflection)

    def test_visual_caption_renders_as_plain_text(self):
        self.screenshot("0002", "state", "Menu with <em>HTML</em> and [link](https://example.invalid)")
        draft = Path(self.run_action("compile")).read_text(encoding="utf-8")
        self.assertIn("[UI state screenshot]", draft)
        self.assertNotIn("<em>HTML</em>", draft)
        self.assertNotIn("[link](https://example.invalid)", draft)
        self.assertIn(r"\<em\>HTML\</em\>", draft)

    def test_themed_narrative_links_specific_receipts_and_preserves_source_sections(self):
        narrative = {
            "overview": [{"text": "[verify] Add the audience.", "sources": []}],
            "themes": [{"title": "Find the next bus", "paragraphs": [
                {"text": "The design evolved toward time order.", "sources": ["0001", "0002", "0002"]},
            ]}],
        }
        output = Path(self.run_action(
            "compile", "--narrative", "-", "--output", "portfolio/draft.md", stdin=json.dumps(narrative),
        ))
        draft = output.read_text(encoding="utf-8")
        self.assertIn("### Find the next bus", draft)
        self.assertIn(
            "The design evolved toward time order. [Decision 1](../docs/decisions/0001-route.md) "
            "[Decision 2](../docs/decisions/0002-route.md)\n",
            draft,
        )
        self.assertIn("## What was avoided and why", draft)
        self.assertIn("## Outcomes", draft)

    def test_rejects_unsourced_prose_and_proposed_ids_before_creating_draft(self):
        for sources in ([], ["0003"], ["9999"]):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                self.run_action(
                    "compile", "--narrative", "-",
                    stdin=json.dumps({"problem": [{"text": "A new design problem.", "sources": sources}]}),
                )
            self.assertFalse((self.log / "drafts").exists())

    def test_narrative_accepts_plain_decision_numbers_and_keeps_legacy_links(self):
        output = Path(self.run_action(
            "compile", "--narrative", "-", stdin=json.dumps({
                "overview": [{"text": "The ordering changed after the first iteration.", "sources": [1, "2", "0002"]}],
            }),
        ))
        draft = output.read_text(encoding="utf-8")
        self.assertIn("The ordering changed after the first iteration. [Decision 1](../0001-route.md) [Decision 2](../0002-route.md)", draft)
        self.assertNotIn("[Receipt 000", draft)

    def test_story_focus_selects_current_decisions_and_chosen_visuals(self):
        self.events.clear()
        self.screenshot("0001", "before", "Earlier list")
        after = self.screenshot("0002", "after", "New list")
        other = self.screenshot("0004", "state", "Old map")
        self.events.append({
            "id": "0004", "kind": "outcome", "record_id": "0002", "date": "2026-11-18",
            "text": "In the hallway test, two riders read the stop sign first.",
            "path": self.log / "events" / "0004-outcome-0002.md",
        })
        narrative = {
            "title": "The next bus first",
            "focus": [2],
            "captures": [2],
            "overview": [{"text": "Time order guided the new list.", "sources": [1, 2]}],
            "themes": [{"title": "Find the next bus", "paragraphs": [
                {"text": "I chose time order over route groups.", "sources": [1, 2]},
            ]}],
            "reflection": [{"text": "[verify] Ask riders if the new order helps.", "sources": []}],
        }
        output = Path(self.run_action(
            "compile", "--edition", "story", "--narrative", "-", stdin=json.dumps(narrative),
        ))
        draft = output.read_text(encoding="utf-8")
        self.assertIn("# The next bus first", draft)
        self.assertIn("**Show next arrival first — human overrule.**", draft)
        self.assertIn("New list", draft)
        self.assertNotIn("Earlier list", draft)
        self.assertNotIn("Old map", draft)
        self.assertNotIn("Unconfirmed idea", draft)
        self.assertNotIn("## What was avoided and why", draft)
        self.assertNotIn("## How AI was used", draft)
        self.assertNotIn("No outcome recorded", draft)
        self.assertIn("In the hallway test", draft)
        self.assertTrue(after.exists())
        self.assertTrue(other.exists())

    def test_story_rejects_unconfirmed_focus_and_unknown_capture(self):
        self.events.clear()
        self.screenshot("0002", "after", "New list")
        for narrative in ({"focus": [3]}, {"captures": [999]}, {"focus": []}):
            with self.subTest(narrative=narrative), self.assertRaises(ValueError):
                self.run_action("compile", "--edition", "story", "--narrative", "-", stdin=json.dumps(narrative))
        self.assertFalse((self.log / "drafts").exists())

    def test_story_default_summarizes_missing_outcomes_once(self):
        self.records["0001"]["effective_status"] = "accepted"
        self.records["0001"]["supersedes"] = None
        output = Path(self.run_action("compile", "--edition", "story"))
        draft = output.read_text(encoding="utf-8")
        self.assertEqual(draft.count("No observed outcome is logged"), 1)
        self.assertIn("## Outcomes and limits", draft)
        self.assertNotIn("No outcome recorded for **", draft)

    def test_drafts_use_distinct_paths_and_explicit_replacement(self):
        first = Path(self.run_action("compile"))
        second = Path(self.run_action("compile"))
        self.assertEqual(second, first.with_stem(f"{first.stem}-2"))
        target = self.root / "chosen-draft.md"
        target.write_text("Existing draft", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Draft already exists"):
            self.run_action("compile", "--output", str(target))
        self.assertEqual(target.read_text(encoding="utf-8"), "Existing draft")
        self.run_action("compile", "--output", str(target), "--overwrite")
        self.assertTrue(target.read_text(encoding="utf-8").startswith("# Case study draft"))

    def test_protects_authoritative_log_and_rejects_empty_drafts(self):
        target = self.records["0001"]["path"]
        target.write_text("Original decision", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside the decision log"):
            self.run_action("compile", "--output", str(target), "--overwrite")
        self.assertEqual(target.read_text(encoding="utf-8"), "Original decision")
        with self.assertRaisesRegex(ValueError, "No confirmed decisions match"):
            self.run_action("compile", "--keyword", "future search")
        with self.assertRaisesRegex(ValueError, "Expected an ISO date"):
            self.run_action("compile", "--from", "20261116")
        self.assertFalse((self.log / "drafts").exists())

    def test_escapes_receipt_links_when_custom_log_contains_spaces(self):
        self.log = self.root / "research notes" / "trade-offs"
        for record in self.records.values():
            record["path"] = self.log / record["path"].name
        self.events[0]["path"] = self.log / "events" / self.events[0]["path"].name
        output = Path(self.run_action("compile", "--output", "case-study.md"))
        self.assertIn("[Decision 1](research%20notes/trade-offs/0001-route.md)", output.read_text())

    def test_rejects_default_drafts_symlink_and_git_metadata(self):
        external = self.root / "external"
        external.mkdir()
        try:
            (self.log / "drafts").symlink_to(external, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symbolic links unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "default drafts directory"):
            self.run_action("compile")
        self.assertEqual(list(external.iterdir()), [])
        with self.assertRaisesRegex(ValueError, "outside Git metadata"):
            self.run_action("compile", "--output", ".git/case-study.md")


if __name__ == "__main__":
    unittest.main()
