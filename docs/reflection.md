# Sprint Reflection

Team 14, Software Engineering Lab
Project: Helping Hands (HH) — Jira project `HH`, repository `dhanush-sr/helping-hands`

## Sprint outcomes

| | Committed | Delivered | Planned close | Actual close |
|---|---|---|---|---|
| Sprint 1 | 29 points | 29 points | 31 Oct | 1 Nov (1 day late) |
| Sprint 2 | 52 points | 52 points | 7 Nov | 10 Nov (3 days late) |

Both sprints delivered their full scope. Neither closed inside its timebox.

## What the merge data shows

Sprint 2 merged three issues in its first three days (11 of 52 points), then
nothing at all between 5 and 8 November. One issue merged on 9 November, and
the remaining **36 points merged on 10 November** — three days after the
sprint was due to close, and 69% of the sprint in a single day.

The burndown reflects this: the line is flat from 4 November onward and does
not reach zero inside the planned dates.

## Root causes

**We over-committed.** Sprint 1 established a velocity of 29 points. We
committed 52 points to Sprint 2, which is 1.8 times what we had evidence we
could deliver. We planned against what we hoped to do rather than what we had
measured.

**We created a merge bottleneck.** We sequenced Sprint 2 as a single serial
dependency chain. The approval story depended on the sign-up stories, and the
notification, schedule, reminder, reports and audit stories all depended on
the approval story. Work that was finished could not be marked Done until its
predecessor had merged, so completed work stayed invisible on the board and
the points landed together at the end instead of spreading across the sprint.

**Our tracking lagged our work.** Because points are only counted at merge,
the four flat days do not mean nobody was working — they mean nothing merged
and nothing moved on the board. Sprint 1's retrospective had already raised
updating Jira daily as an action item, and we did not follow through on it.

## What we will do differently

1. Cap sprint commitment at measured velocity. On this evidence that is
   roughly 29 points, not 52.
2. Identify dependency chains during sprint planning and break them, so that
   more than one person can finish and close work on any given day.
3. Merge daily. Long-lived branches hide progress and force an end-of-sprint
   pile-up.
4. Connect GitHub to Jira so issue transitions follow merges automatically,
   rather than depending on someone remembering to move a card.
5. Treat the burndown as a signal during the sprint, not a report produced
   after it. A line that has been flat for two days is the point at which to
   re-plan, not something to explain afterwards.

## What went well

All 20 backlog issues were delivered through feature branches and reviewed
pull requests into a protected `main`, with CI passing on every merge. The
estimates themselves were sound: the two 8-point stories were correctly
identified as the largest pieces and were the largest in practice. Our
problem was sprint-level planning and tracking discipline, not estimation or
delivery.
