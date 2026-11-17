import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


HOOKS = Path(__file__).resolve().parents[1] / "skills" / "design-receipts" / "hooks"


@unittest.skipUnless(shutil.which("git"), "hook tests require Git")
class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool_path = os.environ["PATH"]
        # Apple's Git shim can start xcodebuild every time a test gets a fresh TMPDIR.
        if sys.platform == "darwin" and shutil.which("git") == "/usr/bin/git":
            resolved = subprocess.run(
                ["xcrun", "--find", "git"], capture_output=True, text=True, timeout=10,
            )
            git = Path(resolved.stdout.strip())
            if resolved.returncode == 0 and git.is_file():
                cls.tool_path = os.pathsep.join((str(git.parent), cls.tool_path))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name) / "hook state"
        self.temp.mkdir()
        self.root = Path(temporary.name) / "design project"
        self.root.mkdir()
        self.log = self.root / "docs" / "decisions"
        self.log.mkdir(parents=True)
        self.index = self.log / "README.md"
        self.index.write_text("<!-- design-receipts:index v1 -->\n")
        (self.log / ".gitignore").write_text("*\n")
        self.page = self.root / "route.md"
        self.page.write_text("Early design\n")
        self.git("-c", "init.templateDir=", "init", "-q")
        self.git("add", "route.md")
        self.git(
            "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgSign=false", "-c", f"core.hooksPath={os.devnull}",
            "commit", "-qm", "Start",
        )

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True,
            env={**os.environ, "PATH": self.tool_path},
        )

    def hook(self, event, host="codex", log_dir=None, command=None, environment=None, **fields):
        payload = {
            "hook_event_name": event,
            "cwd": str(self.root),
            "session_id": "example session",
            "prompt": "private prompt text",
            "transcript_path": str(self.root / "private transcript"),
            **fields,
        }
        if host == "codex" and "turn_id" not in payload:
            payload["turn_id"] = "example turn"
        args = [sys.executable, "-S", str(HOOKS / "nudge.py"), host]
        if log_dir:
            args.extend(["--log-dir", log_dir])
        if command:
            args = ["sh", "-c", command]
        completed = subprocess.run(
            args,
            cwd=payload["cwd"],
            env={
                **os.environ,
                "TMPDIR": str(self.temp),
                "TEMP": str(self.temp),
                "TMP": str(self.temp),
                "CLAUDE_PROJECT_DIR": str(self.root),
                "PATH": os.pathsep.join((str(Path(sys.executable).parent), self.tool_path)),
                **(environment or {}),
            },
            input=json.dumps(payload),
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        self.assertEqual(completed.stderr, "")
        return json.loads(completed.stdout) if completed.stdout else {}

    def assert_nudge(self, output):
        self.assertEqual(set(output), {"systemMessage"})
        self.assertIn("design trade-off", output["systemMessage"])

    def test_new_work_nudges_once_and_consumes_baseline(self):
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        baseline, = list(self.temp.rglob("*.json"))
        self.assertNotIn("private prompt text", baseline.read_text())
        self.assertNotIn(str(self.root), baseline.read_text())
        self.page.write_text("Updated design with a new choice\n")
        self.assert_nudge(self.hook("Stop"))
        self.assertEqual(self.hook("Stop"), {})
        self.assertEqual(list(self.temp.rglob("*.json")), [])

    def test_already_dirty_file_can_change_further(self):
        self.page.write_text("Already dirty\n")
        self.hook("UserPromptSubmit", host="claude")
        self.page.write_text("Already dirty with more changes\n")
        self.assert_nudge(self.hook("Stop", host="claude"))

    def test_removing_tracked_file_counts_as_work(self):
        self.hook("UserPromptSubmit")
        self.page.unlink()
        self.assert_nudge(self.hook("Stop"))

    def test_rebuilding_index_and_opening_existing_files_stays_quiet(self):
        self.hook("UserPromptSubmit")
        self.page.read_text()
        self.index.write_text("<!-- design-receipts:index v1 -->\n# Rebuilt index\n")
        self.assertEqual(self.hook("Stop"), {})

    def test_record_creation_and_later_outcomes_suppress_reminders(self):
        self.hook("UserPromptSubmit")
        self.page.write_text("Updated design\n")
        (self.log / "0001-show-route-details-on-demand.md").write_text("# Receipt\n")
        self.assertEqual(self.hook("Stop"), {})

        self.hook("UserPromptSubmit")
        self.page.write_text("Updated again after testing\n")
        events = self.log / "events"
        events.mkdir()
        (events / "0001-outcome-0001.md").write_text("# Observed outcome\n")
        self.assertEqual(self.hook("Stop"), {})

    def test_removing_a_receipt_does_not_count_as_capture(self):
        receipt = self.log / "0001-show-route-details-on-demand.md"
        receipt.write_text("# Receipt\n")
        self.hook("UserPromptSubmit")
        self.page.write_text("Updated design\n")
        receipt.unlink()
        self.assert_nudge(self.hook("Stop"))

    def test_screenshot_attachment_suppresses_reminder(self):
        self.hook("UserPromptSubmit")
        self.page.write_text("Updated design with screenshot evidence\n")
        bundle = self.log / "events" / "0001-screenshot-0001"
        bundle.mkdir(parents=True)
        (bundle / "README.md").write_text("# Screenshot for 0001\n")
        self.assertEqual(self.hook("Stop"), {})

    def test_alternate_log_and_nested_working_directory(self):
        alternate = self.root / "notes with spaces"
        shutil.move(str(self.log), alternate)
        nested = self.root / "src"
        nested.mkdir()
        fields = {"log_dir": alternate.name, "cwd": str(nested)}
        self.hook("UserPromptSubmit", **fields)
        (nested / "new.txt").write_text("Implementation\n")
        self.assert_nudge(self.hook("Stop", **fields))

    def test_missing_or_expired_baselines_stay_quiet(self):
        self.assertEqual(self.hook("Stop"), {})
        self.hook("UserPromptSubmit")
        baseline, = list(self.temp.rglob("*.json"))
        expired = time.time() - 13 * 60 * 60
        os.utime(baseline, (expired, expired))
        self.page.write_text("Updated design\n")
        self.assertEqual(self.hook("Stop"), {})

    def test_plan_mode_and_continuations_stay_quiet(self):
        self.assertEqual(self.hook("UserPromptSubmit", permission_mode="plan"), {})
        self.assertEqual(list(self.temp.rglob("*.json")), [])
        self.hook("UserPromptSubmit")
        self.page.write_text("Updated design\n")
        self.assertEqual(self.hook("Stop", stop_hook_active=True), {})

    def test_separate_turns_and_sessions_have_separate_baselines(self):
        self.hook("UserPromptSubmit")
        self.page.write_text("Updated design\n")
        self.assertEqual(self.hook("Stop", turn_id="unrelated turn"), {})
        self.assertEqual(self.hook("Stop", session_id="unrelated session"), {})
        self.assert_nudge(self.hook("Stop"))

    def test_foreign_decision_directory_stays_quiet(self):
        self.index.write_text("# Existing project decision docs\n")
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        self.assertEqual(list(self.temp.rglob("*.json")), [])

    def test_non_git_directory_stays_quiet(self):
        self.assertEqual(self.hook("UserPromptSubmit", cwd=str(self.temp)), {})
        self.assertEqual(self.hook("Stop", cwd=str(self.temp)), {})

    @unittest.skipUnless(shutil.which("sh"), "example hook configurations require a POSIX shell")
    def test_config_commands_work_with_space_in_checkout_path(self):
        for host, location in (("codex", ".agents"), ("claude", ".claude")):
            with self.subTest(host=host):
                destination = self.root / location / "skills" / "design-receipts" / "hooks"
                destination.mkdir(parents=True)
                shutil.copyfile(HOOKS / "nudge.py", destination / "nudge.py")
                config = json.loads((HOOKS / f"{host}.json").read_text())["hooks"]
                start = config["UserPromptSubmit"][0]["hooks"][0]["command"]
                stop = config["Stop"][0]["hooks"][0]["command"]
                self.assertEqual(self.hook("UserPromptSubmit", host=host, command=start), {})
                self.page.write_text(f"Updated design for {host}\n")
                self.assert_nudge(self.hook("Stop", host=host, command=stop))

    def use_global_preset(self, host, event, environment):
        preset = json.loads((HOOKS / f"{host}-global.json").read_text())["hooks"]
        command = preset[event][0]["hooks"][0]["command"]
        return self.hook(event, host=host, command=command, environment=environment)

    def install_user_hook(self, config_dir):
        destination = config_dir / "skills" / "design-receipts" / "hooks"
        destination.mkdir(parents=True)
        shutil.copyfile(HOOKS / "nudge.py", destination / "nudge.py")

    @unittest.skipUnless(shutil.which("sh"), "example hook configurations require a POSIX shell")
    def test_global_configs_run_with_only_a_user_install(self):
        user_dir = self.temp.parent / "user home"
        environment = {"HOME": str(user_dir), "CLAUDE_CONFIG_DIR": ""}
        for host, location in (("codex", ".agents"), ("claude", ".claude")):
            with self.subTest(host=host):
                self.install_user_hook(user_dir / location)
                self.assertEqual(self.use_global_preset(host, "UserPromptSubmit", environment), {})
                self.page.write_text(f"Changed design with globally installed {host} hook\n")
                self.assert_nudge(self.use_global_preset(host, "Stop", environment))

        self.index.unlink()
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                self.assertEqual(self.use_global_preset(host, "UserPromptSubmit", environment), {})
                self.page.write_text(f"Changed design without an initialized {host} log\n")
                self.assertEqual(self.use_global_preset(host, "Stop", environment), {})
        self.assertEqual(list(self.temp.rglob("*.json")), [])

    @unittest.skipUnless(shutil.which("sh"), "example hook configurations require a POSIX shell")
    def test_claude_global_config_accepts_custom_user_config_directory(self):
        config_dir = self.temp.parent / "custom claude config"
        self.install_user_hook(config_dir)
        environment = {"HOME": str(self.temp.parent / "user home"), "CLAUDE_CONFIG_DIR": str(config_dir)}
        self.assertEqual(self.use_global_preset("claude", "UserPromptSubmit", environment), {})
        self.page.write_text("Changed design with custom Claude config\n")
        self.assert_nudge(self.use_global_preset("claude", "Stop", environment))

    @unittest.skipUnless(shutil.which("sh"), "example hook configurations require a POSIX shell")
    def test_global_configs_never_fall_back_to_project_scripts(self):
        user_dir = self.temp.parent / "user home"
        environment = {"HOME": str(user_dir), "CLAUDE_CONFIG_DIR": ""}
        for host, location in (("codex", ".agents"), ("claude", ".claude")):
            with self.subTest(host=host):
                project_hook = self.root / location / "skills" / "design-receipts" / "hooks" / "nudge.py"
                project_hook.parent.mkdir(parents=True)
                project_hook.write_text('raise RuntimeError("ran a project script from a user preset")\n')
                self.assertEqual(self.use_global_preset(host, "UserPromptSubmit", environment), {})
                self.page.write_text(f"Changed design without a user-level {host} install\n")
                self.assertEqual(self.use_global_preset(host, "Stop", environment), {})
        relative_config = {**environment, "CLAUDE_CONFIG_DIR": ".claude"}
        self.assertEqual(self.use_global_preset("claude", "UserPromptSubmit", relative_config), {})
        self.assertEqual(self.use_global_preset("claude", "Stop", relative_config), {})


if __name__ == "__main__":
    unittest.main()
