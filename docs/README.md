# Project documentation

| Document | Contents |
|---|---|
| [reflection.md](reflection.md) | Sprint outcomes, root causes and process improvements |
| [Sprint_Reflection.md](Sprint_Reflection.md) | Long-form reflection answering the four handout questions |
| [screenshots/](screenshots/) | Jira evidence (see checklist below) |

## Screenshot checklist

Export these from https://dhanred0309.atlassian.net (project key `HH`) and
place them in `docs/screenshots/` using exactly these filenames:

- [x] `jira_dashboard.png` — Reports view: work items by status, type and assignee
- [x] `product_backlog.png` — work item details table (full data in `../product_backlog.csv`)
- [x] `sprint_backlog.png` — Sprint 2 burnup report with the sprint-start work item list
- [x] `sprint_progress.png` — velocity report, commitment against completed for both sprints
- [x] `burndown_chart.png` — Sprint 2 burndown
- [x] `burndown_sprint1.png` — Sprint 1 burndown

Both sprints are closed, so the board and backlog views are empty; the
equivalent evidence is taken from the Reports views instead.

## Sprint metrics

| | Issues | Committed | Delivered | Planned close | Actual close |
|---|---|---|---|---|---|
| Sprint 1 (27–31 Oct) | 8 | 29 pts | 29 pts | 31 Oct, 23:00 | 1 Nov, 00:43 |
| Sprint 2 (02–07 Nov) | 12 | 52 pts | 52 pts | 7 Nov | 10 Nov |
| **Total** | **20** | **81 pts** | **81 pts** | | |

7 epics. 6 further stories were merged into others during refinement and
closed against the issue that absorbed them.

All 20 issues were delivered through feature branches and reviewed pull
requests into a protected `main`, with CI passing on every merge.

## Reading the Sprint 1 charts

Every work item was created in Jira on 31 October, the last day of Sprint 1.
The backlog was agreed and the work was underway before that, but it was not
entered into Jira until the end of the sprint.

Two things follow, and both are visible in the screenshots:

- The velocity report shows Sprint 1 with a commitment of 0 and 29 points
  completed. Jira records commitment as the scope present when a sprint
  starts, and the issues were added afterwards.
- The Sprint 1 burndown sits at zero until 31 October and then rises and
  falls inside a single day, because that is when the scope entered the
  sprint.

Sprint 2 does not have this problem: its scope was in place at the start, so
its commitment reads 52 and its burndown covers the whole sprint window.
