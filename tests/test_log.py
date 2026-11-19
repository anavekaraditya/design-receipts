import base64
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CLI = Path(__file__).resolve().parents[1] / "skills" / "design-receipts" / "scripts" / "receipts.py"
RECEIPT = {
    "title": "Keep the stop list scannable",
    "date": "2026-03-05",
    "context": "Riders scan a dense list of stops for a particular name.",
    "decision": "Reveal arrivals after the rider selects a stop.",
    "options": "- Chosen: Reveal arrivals on tap.\n- Alternative: Display arrivals inline.",
    "rejections": "Inline arrivals compete for room with stop names.",
    "tradeoffs": "Riders take one extra step to see arrivals.",
    "ai_roles": ["Proposed by AI", "Decided by human", "Overruled by human"],
}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X0ZkAAAAASUVORK5CYII=")


class ReceiptLogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.log = self.root / "docs" / "decisions"
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True)

    def cli(self, *args, data=None, ok=True):
        result = subprocess.run(
            [sys.executable, "-SB", str(CLI), *args], cwd=self.root,
            input=json.dumps(data) if data is not None else "",
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode == 0, ok, result.stderr or result.stdout)
        return result.stdout if ok else result.stderr

    def seed(self, **fields):
        self.cli("init")
        return self.cli("capture", "--confirmed", data={**RECEIPT, **fields})

    def record(self, receipt_id):
        candidates = list(self.log.glob(f"{int(receipt_id)}-*.md"))
        if not candidates:
            candidates = list(self.log.glob(f"{int(receipt_id):04d}-*.md"))
        record, = candidates
        return record

    def test_new_private_log_and_idempotent_init(self):
        self.seed()
        contents = self.record("0001").read_bytes()
        self.assertIn("existing log", self.cli("init"))
        self.assertEqual(self.record("0001").read_bytes(), contents)
        self.assertEqual(self.git("status", "--short", "--untracked-files=all").stdout, "")
        self.assertIn("Valid log: 1 decision(s)", self.cli("validate"))

    def test_plain_numbers_work_across_the_decision_lifecycle(self):
        self.cli("init")
        self.assertIn("Saved Decision 1", self.cli("capture", data=RECEIPT))
        decision = self.log / "1-keep-the-stop-list-scannable.md"
        self.assertTrue(decision.exists())
        self.assertIn("# Decision 1 —", decision.read_text(encoding="utf-8"))
        self.cli("accept", "1", "--confirmed")
        self.cli("outcome", "1", "--confirmed", data={"text": "The prototype has the intended tap target."})
        self.assertTrue((self.log / "events" / "1-outcome-1.md").exists())
        successor = {**RECEIPT, "title": "Expand the selected stop", "date": "2026-03-06"}
        self.cli("supersede", "1", "--confirmed", data=successor)
        self.assertTrue((self.log / "2-expand-the-selected-stop.md").exists())
        self.cli("deprecate", "2", "--confirmed", data={"text": "The prototype phase ended."})
        self.assertIn("Decision 2", self.cli("review"))
        self.cli("validate")

    def test_events_stay_in_number_order_after_nine_entries(self):
        self.seed()
        for number in range(1, 12):
            self.cli("outcome", "1", "--confirmed", data={"text": f"Prototype observation {number}."})
        evidence = json.loads(self.cli("evidence"))
        self.assertEqual([int(event["id"]) for event in evidence["events"]], list(range(1, 12)))

    def test_legacy_records_events_and_screenshots_still_work_with_plain_numbers(self):
        self.seed()
        decision = self.record("1")
        legacy = decision.with_name("0001-keep-the-stop-list-scannable.md")
        content = decision.read_text(encoding="utf-8").replace("# Decision 1 —", "# 0001 —", 1)
        decision.unlink()
        legacy.write_text(content, encoding="utf-8")
        events = self.log / "events"
        events.mkdir()
        outcome = events / "0001-outcome-0001.md"
        outcome.write_text("# Outcome for 0001\n\nDate: 2026-03-06\n\nPrototype reviewed.\n", encoding="utf-8")
        screenshot = events / "0002-screenshot-0001"
        screenshot.mkdir()
        (screenshot / "image.png").write_bytes(PNG)
        metadata = screenshot / "README.md"
        metadata.write_text(
            "# Screenshot for 0001\n\nDate: 2026-03-06\nState: after\nRoute: /stops\n"
            "Viewport: 1x1\nCaption: Legacy screenshot\n\n![Screenshot](image.png)\n", encoding="utf-8",
        )
        original = {path: path.read_bytes() for path in (legacy, outcome, metadata)}
        self.cli("reindex")
        self.cli("validate")
        self.cli("outcome", "1", "--confirmed", data={"text": "A second review confirmed the target."})
        self.assertTrue((events / "3-outcome-1.md").exists())
        self.cli("capture", "--supersedes", "1", "--confirmed", data={**RECEIPT, "title": "New direction"})
        draft = Path(self.cli("compile", "--edition", "archive").strip()).read_text(encoding="utf-8")
        self.assertIn("[Decision 1](../0001-keep-the-stop-list-scannable.md)", draft)
        self.assertIn("[Decision 2](../2-new-direction.md)", draft)
        self.assertIn("../events/0002-screenshot-0001/image.png", draft)
        self.assertNotIn("Receipt 0001", draft)
        for path, value in original.items():
            self.assertEqual(path.read_bytes(), value)
        self.cli("validate")

    def test_existing_decisions_are_preserved_and_alternate_can_be_tracked(self):
        self.log.mkdir(parents=True)
        index = self.log / "README.md"
        index.write_text("# Our old decisions\n", encoding="utf-8")
        self.assertIn("belongs to another log", self.cli("init", ok=False))
        self.assertEqual(index.read_text(encoding="utf-8"), "# Our old decisions\n")
        self.assertFalse((self.log / "template.md").exists())
        self.cli("--log-dir", "notes/ux choices", "init", "--track")
        self.cli("--log-dir", "notes/ux choices", "capture", "--confirmed", data=RECEIPT)
        self.assertIn("notes/ux choices/1-", self.git("-c", "core.quotePath=false", "status", "--short", "--untracked-files=all").stdout)
        for unsafe in (".git/log", "../elsewhere", str(self.root)):
            self.cli("--log-dir", unsafe, "init", ok=False)

    def test_incomplete_note_stays_proposed_even_with_confirmed_flag(self):
        self.cli("init")
        self.assertIn("proposed", self.cli("capture", "--confirmed", data={"title": RECEIPT["title"]}))
        record = self.record("0001")
        self.assertIn("[verify]", record.read_text(encoding="utf-8"))
        self.assertIn("still proposed", self.cli("accept", "0001", "--confirmed", ok=False))
        self.assertIn("--confirmed", self.cli("accept", "0001", ok=False))
        self.cli("accept", "0001", "--update", "--confirmed", data=RECEIPT)
        self.assertIn("Status: accepted", record.read_text(encoding="utf-8"))
        self.assertIn("outcome pending", self.cli("review"))

    def test_init_preserves_tracked_paths_even_if_the_worktree_copy_is_missing(self):
        self.log.mkdir(parents=True)
        previous = self.log / "0001-keep-the-stop-list-scannable.md"
        previous.write_text("Tracked history\n", encoding="utf-8")
        self.git("add", str(previous.relative_to(self.root)))
        previous.unlink()
        self.assertIn("Git already tracks files", self.cli("init", ok=False))
        self.assertEqual(list(self.log.iterdir()), [])

    def test_title_cannot_corrupt_the_record_header(self):
        self.cli("init")
        for separator in ("\n", "\r", "\u2028"):
            with self.subTest(separator=repr(separator)):
                self.assertIn("Invalid text for title", self.cli(
                    "capture", "--confirmed", data={**RECEIPT, "title": f"First line{separator}Second line"}, ok=False,
                ))
        self.assertIn("Saved Decision 1", self.cli("capture", "--confirmed", data=RECEIPT))
        self.cli("validate")

    def test_unmeasured_outcome_stays_visible_in_review_and_draft(self):
        self.seed(outcome="No outcome has been measured yet.")
        self.assertIn("outcome pending", self.cli("review"))
        output = Path(self.cli("compile", "--edition", "archive").strip())
        self.assertIn("[verify] No outcome recorded", output.read_text(encoding="utf-8"))
        self.assertIn("known observation", self.cli("outcome", "0001", "--confirmed", data={"text": "Unmeasured."}, ok=False))

    def test_known_outcome_stays_in_the_draft_alongside_an_open_measurement(self):
        outcome = "Two walkthroughs confirmed the extra tap. [verify] Measure scanning time."
        self.seed(outcome=outcome)
        output = Path(self.cli("compile", "--edition", "archive").strip())
        self.assertIn(outcome, output.read_text(encoding="utf-8"))

    def attach(self, record_id, source, *flags, state="after", route="/stops", ok=True):
        return self.cli(
            "attach-screenshot", record_id, str(source), "--state", state, "--route", route,
            "--caption", "Selected stop shows one arrival", *flags, ok=ok,
        )

    def test_screenshots_attach_to_proposals_and_accepted_receipts_without_editing_them(self):
        self.cli("init")
        self.cli("capture", data=RECEIPT)
        proposal = self.record("0001").read_bytes()
        source = self.root / "screenshot.png"
        source.write_bytes(PNG)
        before = self.log / "events" / "1-screenshot-1"
        self.attach("0001", source, "--date", "2026-03-04", state="before")
        self.assertEqual(self.record("0001").read_bytes(), proposal)
        self.assertFalse(json.loads(self.cli("evidence"))["events"])
        self.assertEqual((before / "image.png").read_bytes(), PNG)
        self.assertIn("Viewport: 1x1", (before / "README.md").read_text(encoding="utf-8"))

        self.cli("accept", "0001", "--confirmed")
        accepted = self.record("0001").read_bytes()
        after = self.log / "events" / "2-screenshot-1"
        self.attach("0001", source, "--viewport", "960x600")
        source.unlink()
        self.assertEqual(self.record("0001").read_bytes(), accepted)
        self.assertEqual((after / "image.png").read_bytes(), PNG)
        self.assertIn("2 screenshots", self.cli("review"))
        self.assertIn("2 event(s)", self.cli("validate"))
        index = (self.log / "README.md").read_text(encoding="utf-8")
        self.assertIn("[Before screenshot](events/1-screenshot-1/README.md)", index)
        self.assertIn("[After screenshot](events/2-screenshot-1/README.md)", index)
        self.assertEqual(self.git("status", "--short", "--untracked-files=all").stdout, "")
        draft = Path(self.cli("compile", "--edition", "archive").strip()).read_text(encoding="utf-8")
        self.assertIn("## Visual evidence", draft)
        self.assertIn("../events/1-screenshot-1/image.png", draft)
        self.assertIn("../events/2-screenshot-1/image.png", draft)
        self.assertIn("[verify] No outcome recorded", draft)

    def test_invalid_screen_evidence_cannot_create_or_break_the_log(self):
        self.seed()
        source = self.root / "invalid.png"
        source.write_bytes(PNG[:-12])
        self.assertIn("PNG", self.attach("0001", source, ok=False))
        source.write_bytes(PNG)
        self.assertIn("without a query or fragment", self.attach("0001", source, route="/stops?token=example", ok=False))
        self.assertIn("viewport", self.attach("0001", source, "--viewport", "abc", ok=False))
        self.assertIn("does not exist", self.attach("0002", source, ok=False))
        self.assertFalse((self.log / "events").exists())
        self.cli("validate")

    def test_validation_catches_a_missing_screenshot_asset(self):
        self.seed()
        source = self.root / "screenshot.png"
        source.write_bytes(PNG)
        self.attach("0001", source)
        (self.log / "events" / "1-screenshot-1" / "image.png").unlink()
        self.assertIn("Expected a regular PNG", self.cli("validate", ok=False))

    def test_complete_draft_waits_for_confirmation_and_malformed_options_are_marked(self):
        self.cli("init")
        self.cli("capture", data=RECEIPT)
        self.assertIn("awaiting confirmation", self.cli("review"))
        self.cli("capture", "--confirmed", data={**RECEIPT, "options": "Inline arrivals or reveal on tap."})
        record = self.record("0002").read_text(encoding="utf-8")
        self.assertIn("Status: proposed", record)
        self.assertIn("Inline arrivals or reveal on tap.\n\n[verify]", record)
        self.cli("capture", "--confirmed", data={
            **RECEIPT, "options": "- Chosen: Text label.\n- Constrained: The spec requires a readable label.",
            "rejections": "None", "ai_roles": ["No AI involvement"],
        })
        self.assertIn("Status: accepted", self.record("0003").read_text(encoding="utf-8"))

    def test_events_and_supersession_keep_accepted_bytes_intact(self):
        self.seed()
        initial = self.record("0001")
        initial_bytes = initial.read_bytes()
        self.cli("outcome", "0001", "--confirmed", data={"text": "The prototype review confirmed the extra tap.", "date": "2026-03-06"})
        successor = {**RECEIPT, "title": "Show the next arrival for the selected stop", "date": "2026-03-07"}
        self.cli("capture", "--supersedes", "0001", data=successor)
        self.assertIn("Accepted (1)", self.cli("review"))
        self.cli("accept", "0002", "--confirmed")
        self.assertIn("Superseded (1)", self.cli("review"))
        self.assertEqual(initial.read_bytes(), initial_bytes)
        self.assertIn("Replaced by [Decision 2]", (self.log / "README.md").read_text(encoding="utf-8"))
        self.cli("supersede", "0001", "--confirmed", data=successor, ok=False)
        second_bytes = self.record("0002").read_bytes()
        self.cli("deprecate", "0002", "--confirmed", data={"text": "Prototype ended before release.", "date": "2026-03-08"})
        self.assertEqual(self.record("0002").read_bytes(), second_bytes)
        self.assertIn("Deprecated (1)", self.cli("review"))
        self.assertIn("2 event(s)", self.cli("validate"))

    def test_index_recovers_from_stale_or_missing_file(self):
        self.seed()
        index = self.log / "README.md"
        expected = index.read_bytes()
        index.write_bytes(expected + b"\nStale\n")
        self.assertIn("stale", self.cli("validate", ok=False))
        self.cli("reindex")
        self.assertEqual(index.read_bytes(), expected)
        index.unlink()
        self.assertIn("missing", self.cli("validate", ok=False))
        self.cli("reindex")
        self.assertEqual(index.read_bytes(), expected)

    def test_invalid_lifecycle_and_duplicate_ids_are_reported(self):
        self.seed()
        record = self.record("0001")
        expected = record.read_text(encoding="utf-8")
        duplicate = self.log / "0001-duplicate.md"
        duplicate.write_text(expected, encoding="utf-8")
        self.assertIn("Duplicate decision number", self.cli("validate", ok=False))
        duplicate.unlink()
        record.write_text(expected.replace("\n\n## Context", "\nSupersedes: 0025\n\n## Context"), encoding="utf-8")
        self.assertIn("invalid predecessor 25", self.cli("validate", ok=False))

    def test_parallel_captures_get_distinct_numbers(self):
        self.cli("init")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            saved = list(pool.map(
                lambda index: self.cli("capture", "--confirmed", data={**RECEIPT, "title": f"Decision {index}"}),
                range(5),
            ))
        self.assertEqual({line.split()[2] for line in saved}, {"1", "2", "3", "4", "5"})
        self.assertIn("5 decision(s)", self.cli("validate"))

    @unittest.skipUnless(hasattr(os, "symlink"), "this platform lacks symbolic links")
    def test_log_location_cannot_follow_symlinks(self):
        alternate = self.root / "alternate"
        alternate.mkdir()
        self.log.parent.mkdir()
        try:
            self.log.symlink_to(alternate, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        self.assertIn("symbolic links", self.cli("init", ok=False))
        self.assertEqual(list(alternate.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
