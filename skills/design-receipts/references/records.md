# Capture and maintain receipts

Use the CLI for writes so required fields, status changes, IDs, and links stay consistent. Read the Markdown records directly for project history. Keep past reasoning intact. Add a receipt if a confirmed choice changes and add a dated entry if new evidence arrives. Use the index or `review` for current status. An accepted receipt retains its original status line after it is superseded or deprecated.

## Draft from what happened

| Field | What to write |
| --- | --- |
| `title` | A decision someone could recall by name. |
| `context` | The problem, constraint, or change that prompted the choice. |
| `decision` | The selected behavior or direction in one or two sentences. |
| `options` | One `- Chosen: …` line and one or more `- Alternative: …` lines. If the choice was constrained to one option, give the reason on a `- Constrained: …` line. |
| `rejections` | Each ruled-out option and the specific reason. Use `None` explicitly when appropriate. |
| `tradeoffs` | The concrete cost or uncertainty the designer agreed to carry. |
| `ai_roles` | One or more supported roles from the list below. |
| `date` | Defaults to today. Use `YYYY-MM-DD` when capturing a known earlier date. |
| `outcome`, `open_questions`, `evidence` | Optional. Leave `outcome` empty until the designer supplies an observation. Use `open_questions` for what still needs testing and `evidence` for relevant links. |

Choose only roles established by the evidence.

- `Proposed by AI` when the agent suggested one of the considered options.
- `Built by AI` when the agent implemented the chosen direction.
- `Verified by human` when the designer or another person checked the work against evidence or tested it.
- `Decided by human` when a person explicitly made the choice.
- `Overruled by human` when a person rejected the agent's recommendation. Name the recommendation and why it was rejected.
- `No AI involvement` on its own when AI was absent from the decision and served at most as a scribe.

A compact preview can fit in three lines.

> **Choice** Reveal arrivals on tap so route names remain easy to scan.\
> **Rejected** AI recommended arrivals inline. The designer found the extra rows crowded the list.\
> **Cost** Riders tap once to see a time. **AI role** Proposed by AI, Decided by human, Overruled by human.

## Save and review

Run the following subcommands after `python3 -SB <skill-directory>/scripts/receipts.py`. Commands that take authored fields read a JSON object from stdin. Pass user-supplied values as data, for example through a quoted heredoc or a standard JSON encoder. Use the exact field keys in the table. Preserve an unresolved value as `[verify]` or omit it from the input. Options are one string with newline-separated Markdown bullets.

| Command | When to use |
| --- | --- |
| `init` | Prepare a new private log. `init --track` makes a new log visible to Git. |
| `capture` | Save receipt JSON as a proposal. Add `--confirmed` only after the designer approves the substantive content. If required evidence is missing, the receipt stays proposed. |
| `accept ID --confirmed` | Accept the existing proposal following designer confirmation. Add `--update` and send only the revised JSON fields when they provide corrections. |
| `capture --supersedes ID` | Save a proposed successor. After confirmation, accept its new number. Direct confirmed replacement uses `supersede ID --confirmed` with receipt JSON. |
| `outcome ID --confirmed` | Append a designer-confirmed observation using JSON with `text` and an optional `date`. Retain uncertainty and any evidence behind the observation. |
| `deprecate ID --confirmed` | Retire a current decision without a successor. Send the reason as JSON `text` and an optional `date`. |
| `attach-screenshot ID PNG` | Attach a local capture to a proposal or accepted receipt. Include `--state`, `--route`, and `--caption`. See the [browser capture workflow](screenshots.md). |
| `review` | List statuses and surface proposals or pending outcomes. |
| `validate` / `reindex` | Check the log and generated index, or rebuild the index from valid records. |

If the CLI says it saved a receipt or event and could not refresh the index, repair the index with `reindex`. The source file already exists.
