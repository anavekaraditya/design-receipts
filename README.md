# Design Receipts

An agent skill for designers who build with AI. It captures the reasoning behind a design change, saves screenshots from the running app, and turns confirmed decisions into a portfolio case-study draft with links to the evidence.

> **Keep a decision trail as we build.**

Say this at the start of a build session.

## Install in your project

You need a Git project, Python 3.10 or newer, and Codex, Cursor, or Claude Code. From the root of the project you’re building, clone the skill beside it.

```sh
git clone https://github.com/anavekaraditya/design-receipts.git ../design-receipts-src
```

Run the commands for your agent.

**Codex or Cursor**

```sh
mkdir -p .agents/skills
cp -R ../design-receipts-src/skills/design-receipts .agents/skills/
```

**Claude Code**

```sh
mkdir -p .claude/skills
cp -R ../design-receipts-src/skills/design-receipts .claude/skills/
```

Open a new agent chat in that project. Invoke `$design-receipts` in Codex or `/design-receipts` in Cursor and Claude Code.

### Install once for all your projects

Use your existing checkout of this repository, or clone it once.

```sh
git clone https://github.com/anavekaraditya/design-receipts.git "$HOME/design-receipts-src"
cd "$HOME/design-receipts-src"
```

From that checkout, run the commands for your agent.

**Codex or Cursor**

```sh
mkdir -p "$HOME/.agents/skills"
cp -R skills/design-receipts "$HOME/.agents/skills/"
```

**Claude Code**

```sh
mkdir -p "$HOME/.claude/skills"
cp -R skills/design-receipts "$HOME/.claude/skills/"
```

Start a new chat in any Git project and invoke the skill there. Each project keeps its own decision log. [Codex skill locations](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) · [Cursor skill locations](https://cursor.com/docs/skills#skill-directories) · [Claude Code skill locations](https://code.claude.com/docs/en/skills#choose-where-skills-load)

## Your first session

1. **Start before editing.** Use the prompt above while the old UI is still available. For a visible change in a runnable web app, the agent can start or reuse the local dev server and capture the same screen or interaction before and after the edit. If the earlier state is already gone, the agent can still attach the after screenshot. [Browser setup and capture guide](skills/design-receipts/references/screenshots.md)
2. **Build as usual.** Talk through choices in the chat. When a meaningful decision comes up, the agent saves a proposed receipt with the choice, rejected alternatives, trade-offs, AI’s role, and any screenshots it captured. Confirm or correct the proposal in one reply. If you only want to capture one decision, say **“Log this decision”** and describe what you chose and why.
3. **Ask for a draft when you need one.** Say **“Compile my confirmed receipts into a case-study draft.”** The Markdown draft links back to the decisions and screenshots. Look for `[verify]` where the evidence leaves a gap, such as an outcome you haven’t measured.

## See what a receipt looks like

In **Routeboard**, a fictional transit app, the AI suggested showing live arrivals under every stop. The designer chose to reveal them on tap so the stop names would be easier to scan. The trade-off was one extra tap.

The [decision receipt](examples/routeboard/decisions/0001-reveal-arrivals-on-tap.md) keeps that reasoning with the project. Later, the draft uses it to tell the story.

> The route list needed to stay easy to scan. I chose to put arrival predictions behind a tap to give stop names more room, accepting one additional step to check the next arrival. [Receipt 0001](examples/routeboard/decisions/0001-reveal-arrivals-on-tap.md)

[Read the complete case-study draft](examples/routeboard/case-study.md) · [Replay the example](examples/routeboard/README.md)

## Find and use your receipts

Open `docs/decisions/README.md` for an index of decisions and their screenshots. Receipts are Markdown files in `docs/decisions/`, and case-study drafts go in `docs/decisions/drafts/` by default. If your project already uses `docs/decisions/`, give the agent a different project-relative folder.

| When you want to | Ask the agent |
| --- | --- |
| See what needs your attention | “Show me the decisions waiting for confirmation.” |
| Preserve a change of direction | “We changed course. Record what replaced receipt 0001 and why.” |
| Add something you learned later | “Add this usability test finding to receipt 0001.” |
| Draft a focused case study | “Compile only the decisions about onboarding.” |

Codex and Claude Code can also show an optional reminder when a turn changes project files. Enable it in one project or across your projects with a decision log. [Reminder setup](skills/design-receipts/references/hooks.md)

## Privacy, updates, and removal

- New logs, screenshots, and default drafts are Git-ignored. Use `init --track` to put a new log under version control. Review the text and images before sharing and keep secrets and personal data out of the record. Your agent handles conversation and receipt text according to its own data settings.
- To update, run `git pull --ff-only` in your checkout of this repository and replace the installed skill folder with the refreshed copy. Start a new agent chat to load it.
- To uninstall, remove any [reminders you installed](skills/design-receipts/references/hooks.md) and delete the installed `design-receipts` skill folder. The decision log and images remain in your project.

## Preview status

The capture, confirmation, and compile workflow was tested in Codex and Cursor. Browser screenshots were verified with a live Chromium run. Claude Code discovered the skill and ran the prompt hook. A signed-in Claude session is still needed to verify the complete flow.

Run the local checks with `python3 -SB -m unittest discover -s tests -v`. [Changelog](CHANGELOG.md) · [MIT License](LICENSE) · [Report a workflow issue](https://github.com/anavekaraditya/design-receipts/issues)
