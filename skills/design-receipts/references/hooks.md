# Optional Capture Reminders

Use the skill once to initialize the project’s decision log before enabling reminders. The included commands use a POSIX shell, Git, and `python3` (version 3.10 or newer).

## Claude Code

1. Install the skill at `.claude/skills/design-receipts/`.
2. Merge the two event groups from [claude.json](../hooks/claude.json) into the `hooks` object of `.claude/settings.local.json`. If either event already has entries, append the new group to its array.
3. Restart Claude Code, trust the project, and inspect the two handlers in `/hooks`. [Claude Code hook setup](https://code.claude.com/docs/en/hooks#hook-locations)

## Codex

1. Install the skill at `.agents/skills/design-receipts/` in the Git root.
2. Merge the two event groups from [codex.json](../hooks/codex.json) into the `hooks` object of `.codex/hooks.json`. If either event already has entries, append the new group to its array. Codex can also load hooks from `.codex/config.toml`. Register each handler in only one place.
3. Restart Codex, trust the project, and use `/hooks` to review and trust these handlers. [Codex hook setup](https://learn.chatgpt.com/docs/hooks#where-codex-looks-for-hooks)

If you initialized a different decision log directory, add `--log-dir "your/project-relative/path"` after `claude` or `codex` in both commands. To disable reminders, remove the two Design Receipts event groups from the host’s configuration.

## What the reminder sees

The hooks compare Git working-tree status and file metadata before and after a turn. A changed working tree with no new receipt or evidence can show one reminder. Git-ignored files, decision log bookkeeping, and install or hook config files are excluded from the working-tree signal. A turn that finishes with a clean checkout at both ends, such as one that commits all changes, may stay quiet. Decisions made in conversation can still be captured by asking the skill directly.

The temporary baseline contains local metadata digests, keyed by host session and checkout. The Stop hook consumes it, and baselines older than 12 hours are ignored. The hook skips when it cannot read a baseline, Git status, or an initialized log. The hook passes no prompt or transcript data to Git and makes no network calls or decision writes.

To check the setup, start a new turn and ask for a small project file change without capturing a receipt. The host should show a reminder when the turn finishes. Try another turn that changes a project file and captures a receipt. That turn should finish quietly.
