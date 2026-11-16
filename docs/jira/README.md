# Jira evidence

Screenshots of the Helping Hands board, exported from
https://dhanred0309.atlassian.net (project key `HH`).

| File | What it shows | Where to find it in Jira |
|---|---|---|
| `01-dashboard.png` | Project dashboard | Project `HH` → Summary |
| `02-product-backlog.png` | Full product backlog with story points | Backlog view, all epics expanded |
| `03-sprint1-backlog.png` | Sprint 1 scope: 8 issues, 29 points | Backlog → Sprint 1 |
| `04-sprint2-backlog.png` | Sprint 2 scope: 12 issues, 52 points | Backlog → Sprint 2 |
| `05-sprint-progress.png` | Board with all issues in Done | Board view |
| `06-burndown-sprint1.png` | Sprint 1 burndown | Reports → Burndown Chart → Sprint 1 |
| `07-burndown-sprint2.png` | Sprint 2 burndown | Reports → Burndown Chart → Sprint 2 |

## Project totals

| | Issues | Points |
|---|---|---|
| Sprint 1 (27–31 Oct) | 8 | 29 |
| Sprint 2 (02–07 Nov) | 12 | 52 |
| **Total** | **20** | **81** |

7 epics, 20 delivered stories and tasks, and 6 stories that were merged into
others during refinement and closed against the issue that absorbed them.

## A note on the Sprint 2 burndown

Sprint 2 was planned for 02–07 Nov. The work was completed, but several
issues were transitioned to Done after the sprint window closed, so the
Sprint 2 burndown does not descend smoothly to zero inside the planned
dates.

The cause was a planning fault rather than a delivery one. We committed 52
points against a measured velocity of 29, and we sequenced the sprint as a
single dependency chain, so finished work could not be closed until its
predecessor had merged. Sprint 1's retrospective had already raised "update
Jira daily" as an action item, and we did not carry it out.

The corrective actions are recorded in `Sprint_Reflection_Helping_Hands.md`:
cap commitment at measured velocity, break serial chains during planning,
and connect GitHub to Jira so transitions follow merges automatically
instead of depending on someone remembering.
