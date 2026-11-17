# 0002 — Show the next arrival for the selected stop

Date: 2026-11-07
Status: accepted
AI roles: Decided by human, Built by AI
Supersedes: 0001

## Context

Riders who already selected a stop still have to open it to check the next arrival.

## Decision

Show one arrival for the selected stop. Keep the other rows collapsed.

## Options considered

- Chosen: Show a prediction only for the selected stop.
- Alternative: Automatically expand the first row.

## Rejected options and why

The first row might show a stop the rider has not selected.

## Trade-offs accepted

The selected row uses one extra line in the route list.

## Open questions

Can riders spot the next arrival without losing their place in the list?
