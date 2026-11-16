# Helping Hands: Sprint Reflection

Team 14, 5th Sem Section B, Software Engineering Lab
Project: Helping Hands (HH), Jira space HH, repo `dhanush-sr/helping-hands`
Sprints covered: HH Sprint 1 (27-31 Oct 2026) and HH Sprint 2 (02-07 Nov 2026)

## Summary

Both sprints were completed and all 20 backlog issues are merged into `main` through
reviewed pull requests with CI passing. Delivery was sound; our sprint planning and our
tracking discipline were not. Sprint 1 overran its timebox by one day and Sprint 2 by three. This document reports that honestly rather than around it.

## 1. Did your estimations reflect the actual effort?

At the story level, mostly yes. The two 8-point stories, HH-24 (approve or decline without
overbooking) and HH-32 (coverage and reports with CSV), were correctly identified as the
largest pieces and were the largest in practice, at roughly 600 and 850 changed lines. The
3-point setup and notification stories were accurate.

At the sprint level, no, and this was our main planning error. We committed **52 points to
Sprint 2** after delivering **29 points in Sprint 1** with the same four people and fewer
working days. That is a 1.8x increase with nothing to justify it; we estimated what we
wanted to finish rather than what we had evidence we could finish.

One story was genuinely underestimated. HH-22 (edit or cancel a shift) was sized at 3
points, but its implementation contained a defect: editing rebuilt a shift's start and end
from a local time of day, which drops the date, so a shift running past midnight in store
time appeared to end before it started and could never be edited. Diagnosing and fixing
that was unplanned work absent from every estimate.

## 2. Was your backlog well-prioritized?

Partly. The ordering was correct, but priority labels were not what produced it.

What worked: the backlog was sequenced by technical dependency, which matched user value
closely enough. Authentication, then stores and busy periods, then posting a shift, then
browsing, then signing up, then approving. Each sprint therefore ended with something
demonstrable rather than a set of disconnected parts.

What did not: we labelled issues High, Medium and Low but scheduled by dependency, so the
labels carried no real weight. HH-32 (reports, 8 points) is lower user value than several
Sprint 2 stories yet sat in the same sprint at the same priority. A stricter reading would
have deferred it and protected the commitment.

## 3. How did your simulated sprint align with your plan?

It did not. Sprint 2 was planned for 02-07 Nov. Issues HH-17 to HH-19 merged on 02, 03 and
04 Nov as intended, then the remaining eight merged on 09 and 10 Nov, after the sprint end
date. The pull request merge history is the accurate record:

| Date | Pull requests merged |
|---|---|
| 31 Oct | #1 HH-8, #2 HH-9, #3 HH-10, #4 HH-11, #5 HH-12 |
| 01 Nov | #6 HH-13, #7 HH-15, #8 HH-16 |
| 02-04 Nov | #9 HH-17, #10 HH-18, #11 HH-19 |
| 09 Nov | #12 HH-20 |
| 10 Nov | #14 HH-22, #15 HH-30, #16 HH-24, #17 HH-27, #18 HH-26, #19 HH-33, #20 HH-28, #21 HH-32 |

Three causes, in order of impact:

1. **A strictly serial dependency chain.** The last seven pieces each built on the one
   before it, so a finished issue could not be merged until its predecessor was in. Work
   that was complete still could not close, and one slow review stalled everything behind
   it. This is the single biggest lesson: we planned the sprint as a queue, not as parallel
   work.
2. **Review and CI latency.** `main` is protected and requires one approval plus passing
   backend and frontend checks. This is correct engineering practice and we are keeping it,
   but we never budgeted for the turnaround it adds, and with four people reviewing each
   other it compounds along a serial chain.
3. **Unplanned defect work.** Two problems surfaced during the sprint: the midnight
   rollover bug in HH-22, and a circular import between the audit and shift services that
   had been passing only because of the order Python happened to load the modules. Both
   needed fixing before dependent work could proceed.

## 4. What insights did the burndown chart give about your team's capacity?

Two, one about the team and one about the chart itself.

**Our sustainable capacity is about 29 points per sprint, not 52.** Sprint 1 is our only
velocity measurement, and we should have planned Sprint 2 against it instead of
against ambition. Had we committed 30 points and moved the rest to a third sprint, the
sprint would have closed on time with the same code written.

**The burndown is only as honest as the status updates behind it.** We did not move issues
to In Progress and Done on the day it happened, so the Sprint 2 chart does not show the
real shape of the work: the remaining-work line stays near its starting value and the
completions fall outside the chart window. The chart is not wrong, it is reporting exactly
what we recorded. The lesson is that the burndown is a tracking instrument, not a reporting
one, and it is worthless if updated retrospectively.

We have deliberately not backdated any transition or edited the sprint dates to hide the
overrun, so the Jira history and the Git history agree with each other.

## What went well

- All 20 issues delivered, 21 pull requests, every one reviewed by a teammate before merge.
- 237 automated backend tests passing, with lint and frontend build enforced in CI.
- The no-overbooking rule (TC-CONC-01 in our Test Plan) is verified with concurrent threads
  and a database row lock, and was checked by removing the lock to confirm the test fails
  without it.
- Continuous deployment of `main` to a test environment after CI passes.
- Two latent defects found and diagnosed during the sprint rather than after it.

## Action items

| # | Action | Owner |
|---|---|---|
| 1 | Cap the next sprint at 30 points, measured from actual velocity | Dhanush |
| 2 | Break serial chains at planning: no more than two dependent issues in sequence | Dhanush |
| 3 | Install GitHub for Jira so merges move issues automatically, instead of relying on memory | Dhanush |
| 4 | Budget review turnaround explicitly; no issue is "done" at code complete | all |
| 5 | Apply the outstanding HH-22 midnight fix, which is not yet in `main` | Aamer |

Sprint 1's retro already recorded "update Jira daily" as an action item and it was not
carried out. Item 3 exists because a process that depends on four people remembering a
manual step is a process that will fail again; automating the transition is the only
version of this fix we trust.
