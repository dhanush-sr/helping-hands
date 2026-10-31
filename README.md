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
    api/deps.py        shared dependencies: sign-in, role and store-scope checks
    api/v1/            versioned endpoints (router.py collects them)
    services/          business rules (auth.py sign-in, access.py roles and store scope)
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

## Demo data

Load the demo data used for testing and the sprint demos (from `backend/`, after
`alembic upgrade head`):

```bash
python -m app.seed            # into an empty database
python -m app.seed --reset    # wipe users, stores, busy periods, shifts and sign-ups, then load again
```

It loads 5 stores with one manager each, 1 admin, 40 volunteers, two busy periods (Diwali
weekend 07-08 Nov 2026 and Weekend rush 14-15 Nov 2026), 26 shifts and 24 sign-ups.

| Who | Email | Password |
|-----|-------|----------|
| Admin | `admin@helpinghands.example` | `Admin@123` |
| Store managers | `manager.koramangala@helpinghands.example`, `manager.indiranagar@...`, `manager.jayanagar@...`, `manager.whitefield@...`, `manager.malleshwaram@...` | `Manager@123` |
| Volunteers | `volunteer01@helpinghands.example` to `volunteer40@helpinghands.example` | `Volunteer@123` |

Demo accounts only: never use these passwords anywhere real.

Shifts for the sign-up edge cases (their description says which test they are for):

| Test | Shift | Set up so that |
|------|-------|----------------|
| TC-SIGN-02 full | Koramangala, Queue management, 07 Nov 16:00-19:00 | both slots are confirmed (status `FILLED`) |
| TC-SIGN-03 clash | Whitefield, Billing counter, 08 Nov 14:00-18:00 | volunteer01 already holds Jayanagar 12:00-16:00 that day |
| TC-SIGN-04 back-to-back | Malleshwaram, Queue management, 08 Nov 17:00-20:00 | volunteer02 already holds Malleshwaram 14:00-17:00 |
| TC-SIGN-05 short notice | Indiranagar, Billing counter | starts 6 hours after the seed runs |

Times are store times (IST); the database stores them in UTC. Volunteers 11 to 30 each have
one pending request on a regular shift, so managers have something to approve.

## Sign in

Endpoints (HH-11). Every other endpoint will need the token as `Authorization: Bearer <token>`.

| Method and path | Does |
|---|---|
| `POST /api/v1/auth/login` | body `{"email": "...", "password": "..."}`; returns `access_token`, `token_type`, `idle_timeout_minutes` and the `user` (id, email, full name, role) |
| `GET /api/v1/auth/me` | the signed-in user |
| `POST /api/v1/auth/logout` | ends the session (204) |

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@helpinghands.example", "password": "Admin@123"}'
```

Rules:
- Wrong email and wrong password both return 401 `INVALID_CREDENTIALS`, so the response never says which one was wrong.
- 5 wrong passwords in a row lock the account for 15 minutes (423 `ACCOUNT_LOCKED`).
- A deactivated account gets 403 `ACCOUNT_DISABLED`.
- A session ends after 30 minutes without a request (401 `SESSION_EXPIRED`), after 12 hours, or on sign-out.
- Passwords are stored only as bcrypt hashes; passwords and tokens are never logged.

The frontend shows a sign-in form, keeps the token in `sessionStorage` (cleared when the tab closes) and has a Sign out button.

## Roles and store access

HH-12 (HH-F-002, HH-SR-004). Every check runs on the server, on every request, and denies by default; hiding a button in the UI is never the protection.

- **Role.** Each endpoint names the roles allowed to call it with a dependency from `app/api/deps.py`: `require_volunteer`, `require_manager`, `require_admin`, `require_manager_or_admin`, `require_any_role`, or `require_role(...)` for another mix. Any other role gets 403 `FORBIDDEN`, before the request body is even looked at.
- **Store scope.** A store manager can only change their own store and its shifts and sign-ups; anything else is 403 `STORE_FORBIDDEN`. Admins work across all stores (where the role check lets them in). Volunteers can only act on their own sign-ups. An id that doesn't exist is 404 (`STORE_NOT_FOUND`, `SHIFT_NOT_FOUND`, `SIGNUP_NOT_FOUND`).

```python
from app.api.deps import require_manager, shift_in_scope
from app.services import access

@router.post("/shifts", status_code=201)
def post_shift(body: ShiftIn, user: User = Depends(require_manager), db: Session = Depends(get_db)):
    store = access.get_store_in_scope(db, user, body.store_id)   # 404 or 403 if not theirs
    ...

@router.patch("/shifts/{shift_id}", dependencies=[Depends(require_manager)])
def edit_shift(body: ShiftEdit, shift: Shift = Depends(shift_in_scope), db: Session = Depends(get_db)):
    ...   # shift is already checked to belong to this manager's store
```

`signup_in_scope` does the same for `/signups/{signup_id}`. The rules live in `app/services/access.py`.

`tests/test_access.py` fails if any endpoint other than `GET /api/v1/health` and `POST /api/v1/auth/login` is missing a sign-in and role check, so a new endpoint can't ship unprotected. It also holds TC-AUTH-03 and TC-AUTH-04, run against stand-in shift and sign-up endpoints until HH-15, HH-22 and HH-24 add the real ones.

All errors, including unknown routes (404), wrong methods (405) and invalid input (422 `VALIDATION_ERROR`), come back as `{"code": "...", "message": "..."}`. Validation messages name the field and the rule but never echo the submitted value.

## Stores and busy periods

HH-13 (HH-F-004, HH-F-005).

| Method and path | Who | Does |
|---|---|---|
| `GET /api/v1/stores` | admin, store manager | admins see every store, a manager sees their own active stores |
| `POST /api/v1/stores` | admin | body `{"name", "location", "manager_id"}` (manager optional); 201 |
| `PATCH /api/v1/stores/{store_id}` | admin | send only what changes: `name`, `location`, `manager_id` (`null` clears it), `is_active` |
| `GET /api/v1/store-managers` | admin | active store managers, for the assign choice |
| `GET /api/v1/busy-periods` | everyone signed in | in date order |
| `POST /api/v1/busy-periods` | admin | body `{"name", "start_date", "end_date"}`; 201 |

Rules:
- Store names are unique (409 `STORE_NAME_TAKEN`).
- A store has at most one manager, who must be an active store manager (400 `INVALID_MANAGER`).
- Stores are deactivated, never deleted, so past shifts and reports stay intact.
- A busy period's end date can't be before its start date (400 `INVALID_DATE_RANGE`); a one-day period is fine.
- Anyone other than an admin gets 403 `FORBIDDEN` for the admin-only calls.

Signed in as the admin, the frontend shows a Stores page (add a store, assign or clear its manager, deactivate) and a Busy periods page (add one, see the list).

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
| `HH_SECRET_KEY`   | a development-only value      | signs session tokens; **set a long random value anywhere shared or deployed** |
| `HH_SESSION_IDLE_MINUTES` | `30`                  | sign-out after this long idle    |
| `HH_MAX_FAILED_LOGINS` / `HH_LOCKOUT_MINUTES` | `5` / `15` | account lockout |

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
