"""Offer a local, non-blocking capture reminder after a turn changes the project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

INDEX_MARKER = b"<!-- design-receipts:index v1 -->"
MESSAGE = "Did this turn settle a design trade-off? Ask Design Receipts to capture it."
RECORD_NAME = re.compile(r"[0-9]+-.+\.md")
SCREENSHOT_BUNDLE = re.compile(r"[0-9]+-screenshot-[0-9]+")
MAX_PATHS = 2000
STATE_MAX_AGE = 12 * 60 * 60
SKILL_PATHS = (".agents/skills/design-receipts", ".claude/skills/design-receipts")
HOOK_CONFIGS = (".claude/settings.local.json", ".codex/hooks.json", ".codex/config.toml")


def git(cwd: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=2,
    ).stdout


def digest(*values: bytes) -> str:
    return hashlib.sha256(b"\0".join(values)).hexdigest()


def signature(path: Path, *, regular_only: bool = False) -> bytes | None:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return None
    if regular_only and not stat.S_ISREG(details.st_mode):
        return None
    return f"{details.st_mode}:{details.st_size}:{details.st_mtime_ns}:{details.st_ctime_ns}".encode()


def changed_project_paths(root: Path, log: Path) -> str:
    status = git(
        root, "status", "--porcelain=v1", "-z", "--no-renames",
        "--untracked-files=all", "--ignore-submodules=all",
    )
    entries = status.rstrip(b"\0").split(b"\0") if status else []
    if len(entries) > MAX_PATHS:
        raise ValueError("working tree has too many changed paths")
    excluded_directories = (log.relative_to(root).as_posix(), *SKILL_PATHS)

    signatures = hashlib.sha256()
    for entry in sorted(entries):
        name = os.fsdecode(entry[3:])
        if name in HOOK_CONFIGS or any(
            name == directory or name.startswith(directory + "/")
            for directory in excluded_directories
        ):
            continue
        signatures.update(entry + b"\0" + (signature(root / name) or b"-") + b"\0")
    return signatures.hexdigest()


def recorded_decisions(log: Path) -> dict[str, str]:
    receipts: dict[str, str] = {}
    events = log / "events"
    event_dirs = (log, events) if events.is_dir() and not events.is_symlink() else (log,)
    for directory in event_dirs:
        for count, path in enumerate(directory.iterdir(), start=1):
            if count > MAX_PATHS:
                raise ValueError("decision log has too many paths")
            if directory == log:
                if not RECORD_NAME.fullmatch(path.name):
                    continue
            elif SCREENSHOT_BUNDLE.fullmatch(path.name) and not path.is_symlink():
                path = path / "README.md"
            elif not path.name.endswith(".md"):
                continue
            content_metadata = signature(path, regular_only=True)
            if content_metadata is not None:
                receipts[digest(os.fsencode(path.relative_to(log)))] = digest(content_metadata)
    return receipts


def private_state_path(host: str, root: Path, log: Path, session: str, turn: str) -> Path:
    # The cache contains only digests. On POSIX also require user-only access to it.
    user_id = getattr(os, "getuid", None)
    suffix = str(user_id()) if user_id else digest(os.fsencode(Path.home()))[:16]
    state_dir = Path(tempfile.gettempdir()) / f"design-receipts-{suffix}"
    state_dir.mkdir(mode=0o700, exist_ok=True)
    details = state_dir.lstat()
    if not stat.S_ISDIR(details.st_mode) or (
        user_id and (details.st_uid != user_id() or stat.S_IMODE(details.st_mode) & 0o077)
    ):
        raise ValueError("temporary state is not private")
    identifier = digest(host.encode(), os.fsencode(root), os.fsencode(log), session.encode(), turn.encode())
    return state_dir / f"{identifier}.json"


def save_state(path: Path, baseline: dict[str, object]) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(baseline, handle)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def consume_state(path: Path) -> dict[str, object]:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        return {}
    with path.open("rb") as handle:
        data = handle.read(512_000)
    path.unlink()
    if not 0 <= time.time() - details.st_mtime <= STATE_MAX_AGE:
        return {}
    baseline = json.loads(data)
    return baseline if isinstance(baseline, dict) else {}


def run(host: str, log_dir: str, payload: dict[str, object]) -> str | None:
    event = payload.get("hook_event_name")
    session = payload.get("session_id")
    cwd = payload.get("cwd")
    if event not in ("UserPromptSubmit", "Stop") or not isinstance(session, str) or not session:
        return None
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return None
    if payload.get("stop_hook_active") or payload.get("permission_mode") == "plan":
        return None

    root = Path(os.fsdecode(git(Path(cwd), "rev-parse", "--show-toplevel").rstrip(b"\n"))).resolve()
    relative_log = Path(log_dir)
    if relative_log.is_absolute() or not relative_log.parts or any(
        part == ".." or part.casefold() == ".git" for part in relative_log.parts
    ):
        return None
    log = root / relative_log
    if log.resolve() != log:
        return None
    index = log / "README.md"
    if signature(index, regular_only=True) is None:
        return None
    with index.open("rb") as handle:
        if handle.readline(128).rstrip(b"\r\n") != INDEX_MARKER:
            return None

    turn_id = payload.get("turn_id")
    state = private_state_path(host, root, log, session, turn_id if isinstance(turn_id, str) else "")
    if event == "UserPromptSubmit":
        state.unlink(missing_ok=True)
        save_state(state, {
            "project": changed_project_paths(root, log),
            "receipts": recorded_decisions(log),
        })
        return None

    baseline = consume_state(state)
    receipts = baseline.get("receipts")
    if not isinstance(receipts, dict) or not isinstance(baseline.get("project"), str):
        return None
    if baseline.get("project") == changed_project_paths(root, log):
        return None
    if any(receipts.get(key) != metadata for key, metadata in recorded_decisions(log).items()):
        return None
    return MESSAGE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=("claude", "codex"))
    parser.add_argument("--log-dir", default="docs/decisions")
    args = parser.parse_args()
    try:
        payload = json.loads(sys.stdin.buffer.read(2_000_000))
        if isinstance(payload, dict):
            message = run(args.host, args.log_dir, payload)
            if message:
                print(json.dumps({"systemMessage": message}))
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError):
        # A reminder is optional. Let either host proceed if local state is unavailable.
        return


if __name__ == "__main__":
    main()
