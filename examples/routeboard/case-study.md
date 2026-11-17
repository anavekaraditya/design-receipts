# Case study draft

> Draft from confirmed decision receipts. Curate before sharing.

## Overview

Routeboard helps riders find a stop and check its arrivals. I explored how much arrival information to show in the stop list. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md) [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

## Problem

Showing arrivals for every stop puts predictions in competition with stop names. Riders who have already selected a stop have a different need. They want to check the next arrival. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md) [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

## Constraints

Every visible prediction takes up space in the list. Hiding predictions behind a tap adds a step for riders who want to check an arrival. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md) [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

## Key decisions and trade-offs

### Keep the stop list easy to scan

The route list needed to stay easy to scan. I chose to put arrival predictions behind a tap to give stop names more room, accepting one additional step to check the next arrival. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md)

I later chose to show one prediction in the list for the selected stop. That uses an extra line in one row and gives the rider who selected it access to the next arrival. [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

[verify] Check whether riders find their next arrival faster in the selected-stop design.

### How the decisions changed

Show one arrival for the selected stop. Keep the other rows collapsed. [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md) supersedes [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md).

Riders who already selected a stop still have to open it to check the next arrival. [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

## What was avoided and why

Inline arrivals compete with the stop names riders are scanning for. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md)

The first row might show a stop the rider has not selected. [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

## How AI was used

**Reveal arrivals on tap** · Proposed by AI, Overruled by human. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md)

**Human overrule.** Show arrivals when a rider taps a stop. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md)

Inline arrivals compete with the stop names riders are scanning for. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md)

**Show the next arrival for the selected stop** · Decided by human, Built by AI. [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

## Outcomes

[verify] No outcome recorded for **Reveal arrivals on tap**. [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md)

The designer checked both states in the prototype. With a stop selected, that row showed one arrival and the other rows showed stop names. With no stop selected, every row showed stop names. Scanning speed was unmeasured. [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md) [Outcome 2026-11-08](decisions/events/0001-outcome-0002.md)

## Reflection

Can riders spot the next arrival without losing their place in the list? [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)

What changed your judgment between [Receipt 0001](decisions/0001-reveal-arrivals-on-tap.md) and [Receipt 0002](decisions/0002-show-the-next-arrival-for-the-selected-stop.md)?
