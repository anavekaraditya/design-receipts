import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "design-receipts" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import export_receipts
from test_log import PNG, RECEIPT


PDF = b"%PDF-1.7\nTest printer output\n%%EOF\n"


class ExportCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.log = self.root / "docs" / "decisions"
        subprocess.run(["git", "-c", "init.templateDir=", "init", "-q", str(self.root)], check=True)
        self.cli("init")
        self.cli("capture", "--confirmed", payload=RECEIPT)
        self.draft = Path(self.cli("compile").strip())
        self.parser = argparse.ArgumentParser()
        export_receipts.add_export_command(self.parser.add_subparsers(required=True))

    def cli(self, *arguments, payload=None):
        result = subprocess.run(
            [sys.executable, "-SB", str(SCRIPTS / "receipts.py"), *arguments],
            cwd=self.root, input="" if payload is None else json.dumps(payload),
            text=True, capture_output=True, check=True,
        )
        return result.stdout

    def export(self, *arguments):
        args = self.parser.parse_args(["export", str(self.draft), *arguments])
        result = io.StringIO()
        with contextlib.redirect_stdout(result):
            args.handler(args, self.root, self.log)
        return Path(result.getvalue().strip())

    def test_exports_edited_prose_and_preserves_source_log(self):
        self.draft.write_text(
            self.draft.read_text(encoding="utf-8") + "\nMy edited reflection stays in the export.\n",
            encoding="utf-8",
        )
        source = {path: path.read_bytes() for path in self.log.rglob("*.md")}
        with patch.object(export_receipts, "print_pdf", return_value=PDF) as printer:
            output = self.export()
        self.assertEqual(output.parent, self.log / "drafts")
        self.assertEqual(output.suffix, ".pdf")
        self.assertEqual(output.read_bytes(), PDF)
        self.assertIn("My edited reflection stays in the export.", printer.call_args.args[0])
        self.assertIn("[verify]", printer.call_args.args[0])
        for path, content in source.items():
            self.assertEqual(path.read_bytes(), content)
        ignored = subprocess.run(["git", "check-ignore", str(output)], cwd=self.root, capture_output=True)
        self.assertEqual(ignored.returncode, 0)

    def test_pdf_collisions_and_explicit_overwrite(self):
        chosen = self.root / "portfolio.pdf"
        with patch.object(export_receipts, "print_pdf", return_value=PDF) as printer:
            first, second = self.export(), self.export()
            self.assertNotEqual(first, second)
            chosen.write_bytes(b"Existing PDF")
            with self.assertRaisesRegex(ValueError, "PDF already exists"):
                self.export("--output", str(chosen))
            self.assertEqual(printer.call_count, 2)
            self.assertEqual(chosen.read_bytes(), b"Existing PDF")
            self.export("--output", str(chosen), "--overwrite")
            self.assertEqual(chosen.read_bytes(), PDF)

    def test_renderer_failure_preserves_draft_and_prior_pdf(self):
        existing = self.root / "case-study.pdf"
        existing.write_bytes(b"Existing PDF")
        original = self.draft.read_bytes()
        with patch.object(export_receipts, "print_pdf", side_effect=ValueError("Browser unavailable")):
            with self.assertRaisesRegex(ValueError, "Browser unavailable"):
                self.export("--output", str(existing), "--overwrite")
        self.assertEqual(existing.read_bytes(), b"Existing PDF")
        self.assertEqual(self.draft.read_bytes(), original)
        self.assertEqual(list(self.log.rglob("*.pdf")), [])

    def test_export_rejects_managed_sources_and_wrong_extensions(self):
        original = self.draft.read_bytes()
        with patch.object(export_receipts, "print_pdf") as printer:
            for output in ("docs/decisions/receipt.pdf", ".git/config.pdf", str(self.draft), "portfolio.html"):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    self.export("--output", output, "--overwrite")
            with self.assertRaisesRegex(ValueError, "Specify --output"):
                self.export("--overwrite")
            printer.assert_not_called()
        self.assertEqual(self.draft.read_bytes(), original)

    def test_screenshot_is_embedded_and_missing_image_does_not_publish(self):
        png = self.root / "state.png"
        png.write_bytes(PNG)
        self.cli("attach-screenshot", "0001", str(png), "--state", "after", "--route", "/stops", "--caption", "Stop list")
        self.draft = Path(self.cli("compile").strip())
        with patch.object(export_receipts, "print_pdf", return_value=PDF) as printer:
            output = self.export()
            self.assertIn("data:image/png;base64,", printer.call_args.args[0])
        image, = self.log.rglob("image.png")
        image.unlink()
        with patch.object(export_receipts, "print_pdf") as printer, self.assertRaises(ValueError):
            self.export("--output", "another.pdf")
        printer.assert_not_called()
        self.assertTrue(output.exists())
        self.assertFalse((self.root / "another.pdf").exists())

    def test_missing_runtime_has_an_actionable_message(self):
        args = self.parser.parse_args(["export", str(self.draft)])
        with tempfile.TemporaryDirectory() as temp, patch.object(export_receipts.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Node.js 18"):
                export_receipts.print_pdf("<h1>Draft</h1>", Path(temp), self.root, args)


if __name__ == "__main__":
    unittest.main()
