# Routeboard example

Routeboard is a fictional transit app. The [decision log](decisions/README.md) and [case-study draft](case-study.md) show how one design choice changed as the designer worked through a prototype.

## Try it with your agent

Install the skill in a scratch Git project, invoke it, and work through these prompts. Confirm each proposed decision when it matches the decision.

> Log this decision. Routeboard helps riders find their stop before they check its arrivals. AI suggested showing arrivals under every stop. I chose tap-to-reveal so riders can scan the stop list. The trade-off is one extra tap.

> We changed course. Once the rider selects a stop, show that stop's next arrival in the list. I rejected expanding the first row because it might show the wrong stop. This costs one extra line for the selected stop. I made the choice and directed AI to build it. Capture it as the successor to Decision 1.

> Record an outcome for Decision 2. I checked both states in the prototype. With a stop selected, that row showed one arrival. The other rows showed stop names. With no stop selected, all rows showed stop names. We haven't measured scanning speed.

> Save a proposal to add a hint to the stop rows, for later review.

> Compile my confirmed Routeboard decisions into a Markdown case-study draft.

The draft should explain the change in direction, surface the human overrule in Decision 1, and mark the effect on riders as `[verify]`.

## Replay with Python

Run this command from the Design Receipts repository. It creates a separate Git project and compiles the bundled example with the local CLI.

```sh
python3 -SB examples/routeboard/replay.py "$(mktemp -d)/routeboard"
```

The replay prints paths to the new project's `decisions/README.md` and `case-study.md`. The command supplies the same fictional evidence and narrative used by the checked-in example.
