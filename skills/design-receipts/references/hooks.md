# Optional Capture Reminders

Reminders are optional. They use a POSIX shell, Git, and `python3` (version 3.10 or newer). Use the skill once to initialize the decision log in each project where you want reminders.

## Choose the preset for your skill install

| Agent | Where the skill is installed | Preset |
| --- | --- | --- |
| Claude Code | Project `.claude/skills/design-receipts/` | [claude.json](../hooks/claude.json) |
| Claude Code | User `~/.claude/skills/design-receipts/` | [claude-global.json](../hooks/claude-global.json) |
| Codex | Project `.agents/skills/design-receipts/` in the Git root | [codex.json](../hooks/codex.json) |
| Codex | User `~/.agents/skills/design-receipts/` | [codex-global.json](../hooks/codex-global.json) |

The global presets run the script from your user installation. If you launch Claude Code with an absolute `CLAUDE_CONFIG_DIR`, put the skill in that directory’s `skills/` folder and use its `settings.json` for user-wide reminders. [Claude Code configuration directory](https://code.claude.com/docs/en/env-vars#configuration-and-state)

## Decide where reminders apply

| Agent | This project only | All your projects with a decision log |
| --- | --- | --- |
| Claude Code | `.claude/settings.local.json` | `~/.claude/settings.json` |
| Codex | `.codex/hooks.json` in the Git root | `~/.codex/hooks.json` in the active user configuration directory |

1. Merge the two event groups from your chosen preset into the settings file’s `hooks` object. If either event already has entries, append the Design Receipts group to its array. Use a global preset for a user-wide settings file. You can also use a global preset in one project’s settings to enable reminders there while keeping the skill installed globally.
2. Register Design Receipts once per agent to avoid duplicate handlers. If you already enabled its project hooks and switch to user-wide reminders, remove those project entries. Codex also accepts hook definitions in `config.toml`. [Claude Code hook locations](https://code.claude.com/docs/en/hooks#hook-locations) · [Codex hook locations](https://learn.chatgpt.com/docs/hooks#where-codex-looks-for-hooks)
3. Restart the agent and trust the project as prompted. Open `/hooks` to inspect the two handlers. In Codex, review and trust the definitions before running them. [Claude Code workspace trust](https://code.claude.com/docs/en/hooks#workspace-trust) · [Codex hook review](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)

For a custom decision log directory, use project settings and add `--log-dir "your/project-relative/path"` after `claude` or `codex` in both commands. To disable reminders, remove the two Design Receipts event groups from the settings file where you added them.

## What the reminder sees

The hooks compare Git working-tree status and file metadata before and after a turn. A changed working tree with no new decision or evidence can show one reminder. Git-ignored files, decision log bookkeeping, and install or hook config files are excluded from the working-tree signal. A turn that finishes with a clean checkout at both ends, such as one that commits all changes, may stay quiet. Decisions made in conversation can still be captured by asking the skill directly.

The temporary baseline contains local metadata digests, keyed by host session and checkout. The Stop hook consumes it, and baselines older than 12 hours are ignored. The hook skips when it cannot read a baseline, Git status, or an initialized log. The hook passes no prompt or transcript data to Git and makes no network calls or decision writes.

To check the setup, start a new turn and ask for a small project file change without capturing a decision. The host should show a reminder when the turn finishes. Try another turn that changes a project file and captures a decision. That turn should finish quietly.
