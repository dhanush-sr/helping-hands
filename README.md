# Helping Hands (HH)

A web app for a retail chain. When stores expect heavy footfall on weekends, holidays and sale days, management staff offer to work a shift in a store. Helping Hands lets stores ask for that help, lets managers sign up for it, and records who turned up.

Software Engineering Lab mini project, Section B, Team 14.

## Team
| Name | SRN | Role | Document lead |
|---|---|---|---|
| Aamer Khan | PES1UG24AM902 | Product Owner | SRS |
| Bhuvan Kumar P | PES1UG24AM069 | Test Engineer | SRS |
| Vivek Varma | PES1UG24AM070 | Developer | SAD |
| Dhanush Shankar Reddy | PES1UG24AM083 | Scrum Master / QA Lead | Test Plan |

## Deliverables
- [Software Requirements Specification (SRS)](SRS_SAD_TestPlan/SRS_Helping_Hands.pdf)
- [Software Architecture and Design Specification (SAD)](SRS_SAD_TestPlan/SAD_Helping_Hands.pdf)
- [Software Test Plan (STP)](SRS_SAD_TestPlan/Test_Plan_Helping_Hands.pdf)

## Tech stack
| Part      | Stack                                   | Folder       |
|-----------|-----------------------------------------|--------------|
| Backend   | Python 3.12, FastAPI, SQLAlchemy 2, Alembic | `backend/`   |
| Database  | PostgreSQL 16 (SQLite for local development) | |
| Frontend  | React 18, Vite                          | `frontend/`  |
| CI        | GitHub Actions                          | `.github/workflows/ci.yml` |

Work is planned in Jira (space Helping Hands, key HH): Sprint 1 27-31 Oct 2026, Sprint 2 02-07 Nov 2026.

## Repository layout

```
backend/
  app/
    main.py            FastAPI app factory (CORS, routers)
    config.py          settings from HH_* environment variables
    api/v1/            versioned endpoints (router.py collects them)
    db/                declarative base, engine, get_db session dependency
    models/            SQLAlchemy models
  alembic/             migrations (alembic.ini in backend/)
  tests/               pytest tests
  requirements.txt     runtime dependencies
  requirements-dev.txt test and lint tools
frontend/
  src/                 React app (App.jsx, api.js)
  vite.config.js       dev server, proxies /api to the backend
.github/workflows/ci.yml
SRS_SAD_TestPlan/      submitted SRS, SAD and Test Plan (do not edit)
```

## Run the backend locally

Needs Python 3.11 or newer.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

- API: http://localhost:8000/api/v1/health → `{"status": "ok", ...}`
- Interactive docs: http://localhost:8000/docs

Create the database (SQLite file `backend/helping_hands.db` by default):

```bash
alembic upgrade head
```

Tests and lint:

```bash
pytest
ruff check .
```

## Run the frontend locally

Needs Node.js 20 or newer.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The page shows whether the backend is reachable; requests to
`/api` are proxied to `http://localhost:8000`, so start the backend first.

Other commands: `npm run lint`, `npm run build` (output in `frontend/dist/`).

## Configuration

Backend settings are read from environment variables with the `HH_` prefix, or from a
`backend/.env` file (never commit it).

| Variable          | Default                       | Meaning                          |
|-------------------|-------------------------------|----------------------------------|
| `HH_ENVIRONMENT`  | `local`                       | shown by the health endpoint     |
| `HH_DATABASE_URL` | `sqlite:///./helping_hands.db`| SQLAlchemy URL (see below)       |
| `HH_CORS_ORIGINS` | `["http://localhost:5173"]`   | JSON list of allowed origins     |

Frontend: `VITE_API_BASE_URL` (build time) when the API is on a different host.

## Database

SQLAlchemy 2 models live in `backend/app/models/`, migrations in `backend/alembic/versions/`.
The same migrations run on SQLite (local) and PostgreSQL (CI and deployed environments):

```bash
export HH_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/helping_hands
alembic upgrade head
```

| Table          | Holds                                                                 |
|----------------|-----------------------------------------------------------------------|
| `users`        | email (unique), name, bcrypt password hash, role (`VOLUNTEER`, `STORE_MANAGER`, `ADMIN`), active flag, failed-login count and lock time |
| `stores`       | name (unique), location, one store manager, active flag                |
| `busy_periods` | name, start date, end date (end not before start)                      |
| `shifts`       | store, optional busy period, task, start/end time (end after start), slots (at least 1), status (`OPEN`, `FILLED`, `CANCELLED`, `COMPLETED`) |
| `signups`      | shift + volunteer (unique pair), status (`REQUESTED`, `CONFIRMED`, `DECLINED`, `WITHDRAWN`), who decided and when |
| `settings`     | admin-editable rules: `weekly_hour_limit` 8, `min_notice_hours` 12, `withdrawal_cutoff_hours` 24 (inserted by the first migration) |

Attendance, notifications and the audit history are added in Sprint 2.

After changing a model, generate a migration and review it before committing:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`:

- **Backend:** install, `ruff check`, `pytest` (models + migrations on SQLite and a
  PostgreSQL 16 service), then `alembic upgrade head` / `downgrade base` on PostgreSQL
- **Frontend:** install, `npm run lint`, `npm run build`

A failing test or lint error turns the pull request check red. Protect `main` in
GitHub (Settings → Branches) and mark both jobs as required checks so nothing merges
on red.

## Workflow

1. Branch from `main`: `feature/HH-<id>-short-name`
2. Commit with the Jira key first: `HH-<id> what changed`
3. Open a pull request to `main` with the Jira key in the title (e.g. `HH-8 ...`)
4. CI must pass and one teammate reviews and approves before merging; nobody approves their own pull request
5. Move the Jira issue to Done once it is merged
