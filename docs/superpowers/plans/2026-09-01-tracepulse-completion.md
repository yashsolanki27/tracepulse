# TracePulse End-to-End Completion Plan

> **STATUS (2026-09-02): All tasks 1–13 executed and committed.** Tasks 1–6, 9–12 in
> earlier commits (see `git log`); Tasks 7, 8, 13 this session. Two manual steps remain
> open below: secret rotation (Task 4) and watching the CI run after push (Task 10).
> Fresh-DB verification (Task 7 Steps 1/4) also pending a manual `docker compose up --build`.

**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every remaining gap between the current TracePulse build (all SPECS.md items done) and a production-complete project: tests, secrets hygiene, docs, frontend completeness, deploy hardening, and CI.

**Architecture:** Work is ordered P0 → P2. Each task is independently shippable and ends with its own commit. Unit tests are pure (no network/DB) and always run; integration tests hit a live `tracepulse_test` Postgres (pgvector) and are auto-skipped when the DB is unreachable, so `pytest -q` works anywhere and CI provides the service container.

**Tech Stack:** FastAPI, SQLAlchemy 2 + pgvector, Alembic, pytest, httpx, React (Vite), Docker Compose, GitHub Actions.

**Spec:** `SPECS.md` (all items complete), `AGENTS.md` (one item at a time, tick, commit; never hand-patch — fix the instruction and redo).

## Global Constraints

- One task = one commit. Tick the plan checkbox after each commit.
- Python code style: modules import flat from `app/` dir (existing pattern uses `sys.path` insertion of `app/`, e.g. `tests/test_ingest.py:12`). Follow it — do NOT restructure into packages.
- Secrets never go into git. `.env` is already gitignored; never "fix" that.
- Frontend talks to the API only via `frontend/src/api.js` helpers; API key is `VITE_API_KEY`.
- CORS middleware in `app/main.py` currently allows only `GET, PATCH` — Task 6 changes this to `GET, POST, PATCH` in the same commit as the frontend create-ticket UI that needs it.
- Never call real Groq/Slack/Gmail APIs from tests. Everything external is mocked.
- Run tests with: `.venv\Scripts\python -m pytest tests -q` (pytest installed by Task 1).

---

### Task 1: Test infrastructure (pytest + conftest + live-test-DB fixtures)

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: pytest in `.venv`; fixture `db_session` (live test DB session; tables truncated between tests); fixture `client` (`fastapi.testclient.TestClient` over `app.main.app` with `get_db` overridden to `db_session`); env `TRACEPULSE_API_KEY=test-key` for the test process; pytest marker `integration` (auto-skipped when the test DB is unreachable).
- Consumed by: Tasks 2, 3, 12, 13.

- [x] **Step 1: Create `requirements-dev.txt`**

```
pytest>=8.0.0
httpx>=0.27.0
```

- [x] **Step 2: Install into the venv**

Run: `.venv\Scripts\pip install -r requirements-dev.txt`
Expected: successful install.

- [x] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
addopts = -q
markers =
    integration: requires a live PostgreSQL+pgvector test DB (auto-skipped if unreachable)
```

- [x] **Step 4: Create `tests/conftest.py`**

```python
"""Shared fixtures: test API key env, live tracepulse_test DB, API client."""
import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

# Set before importing app modules (auth, database, notifications read env).
os.environ.setdefault("TRACEPULSE_API_KEY", "test-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/tracepulse_test",
)
os.environ.pop("SLACK_WEBHOOK_URL", None)  # never hit a real webhook from tests
os.environ.pop("EMAIL_IMAP_HOST", None)    # never start the email poller in tests

TEST_DB_URL = os.environ["DATABASE_URL"]


def _db_available() -> bool:
    try:
        import sqlalchemy
        eng = sqlalchemy.create_engine(TEST_DB_URL, connect_args={"connect_timeout": 2})
        with eng.connect():
            return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if _db_available():
        return
    skip = pytest.mark.skip(reason="live tracepulse_test DB not available")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def db_engine():
    from sqlalchemy import create_engine
    from models import Base
    eng = create_engine(TEST_DB_URL)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture

### Task 2: Unit tests for pure logic (auth, schemas, RCA, SLA, notifications)

**Files:**
- Create: `tests/test_units.py`

**Interfaces:**
- Consumes: `app/auth.py:verify_api_key`, `app/schemas.py` (models + `ALLOWED_TRANSITIONS`), `app/rca.py:analyze_ticket/_clean_triage`, `app/sla.py:compute_deadline/check_slas`, `app/notifications.py:notify_assignment`.
- Produces: regression coverage for the core pipeline without network or DB.

- [x] **Step 1: Write `tests/test_units.py`** (part 1 of 2)

```python
"""Pure unit tests — no network, no DB. External calls mocked."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from fastapi import HTTPException  # noqa: E402


class TestAuth(unittest.TestCase):
    def test_missing_key_401(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {"TRACEPULSE_API_KEY": "secret"}):
            with self.assertRaises(HTTPException) as cm:
                verify_api_key(None)
            self.assertEqual(cm.exception.status_code, 401)

    def test_wrong_key_401(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {"TRACEPULSE_API_KEY": "secret"}):
            with self.assertRaises(HTTPException) as cm:
                verify_api_key("nope")
            self.assertEqual(cm.exception.status_code, 401)

    def test_correct_key_ok(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {"TRACEPULSE_API_KEY": "secret"}):
            self.assertIsNone(verify_api_key("secret"))

    def test_unconfigured_500(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as cm:
                verify_api_key("anything")
            self.assertEqual(cm.exception.status_code, 500)


class TestSchemas(unittest.TestCase):

- [x] **Step 2: Append to `tests/test_units.py`** (part 2 of 2)

```python
def _fake_completion(payload: dict):
    """Mock OpenAI chat response whose message content is `payload` as JSON."""
    msg = mock.Mock()
    msg.content = json.dumps(payload)
    resp = mock.Mock()
    resp.choices = [mock.Mock(message=msg)]
    return resp


VALID_RCA = {
    "root_cause": "deadlock", "evidence": "lock log", "issue_area": "db",
    "suggested_resolution": "add index", "priority": "HIGH",
    "severity": "major", "issue_type": "bug", "team": "platform",
}


class TestRca(unittest.TestCase):
    def test_valid_rca_and_triage(self):
        import rca
        with mock.patch.object(rca, "_client") as c:
            c.return_value.chat.completions.create.return_value = _fake_completion(VALID_RCA)
            out = rca.analyze_ticket("t", "d", "l")
        self.assertEqual(out["root_cause"], "deadlock")
        self.assertEqual(out["priority"], "high")  # normalized lowercase
        self.assertEqual(out["severity"], "major")

    def test_invalid_triage_value_dropped(self):
        import rca
        data = dict(VALID_RCA, priority="apocalypse")
        with mock.patch.object(rca, "_client") as c:
            c.return_value.chat.completions.create.return_value = _fake_completion(data)
            out = rca.analyze_ticket("t", "d", "l")
        self.assertIsNone(out["priority"])

    def test_none_on_garbage_after_retry(self):
        import rca
        bad = mock.Mock()
        bad.content = "not json"
        with mock.patch.object(rca, "_client") as c:
            c.return_value.chat.completions.create.return_value = mock.Mock(
                choices=[mock.Mock(message=bad)])
            self.assertIsNone(rca.analyze_ticket("t", "d", "l"))
            self.assertEqual(c.return_value.chat.completions.create.call_count, 2)


class TestSla(unittest.TestCase):
    def test_deadline_by_priority(self):
        from sla import SLA_HOURS, compute_deadline
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for prio, hours in SLA_HOURS.items():
            self.assertEqual(compute_deadline(created, prio), created + timedelta(hours=hours))

    def test_deadline_null_priority_default(self):
        from sla import DEFAULT_SLA_HOURS, compute_deadline
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(
            compute_deadline(created, None), created + timedelta(hours=DEFAULT_SLA_HOURS))

    def _ticket(self, sla_status=None, status="open", created=None, target=None):
        t = mock.Mock()
        t.sla_status = sla_status
        t.status = status
        now = datetime.now(timezone.utc)
        t.created_at = created or (now - timedelta(minutes=1))
        t.target_resolution_time = target or (now + timedelta(hours=10))
        return t

    def _run(self, tickets):
        import sla
        with mock.patch("sla.SessionLocal") as s, mock.patch("sla.or_", lambda *a: True):
            s.return_value.query.return_value.filter.return_value.filter.return_value \
                .all.return_value = tickets
            sla.check_slas()

    def test_breach(self):
        t = self._ticket(target=datetime.now(timezone.utc) - timedelta(minutes=1))
        self._run([t])
        self.assertEqual(t.sla_status, "breached")

    def test_warning_at_80pct(self):
        now = datetime.now(timezone.utc)
        t = self._ticket(created=now - timedelta(hours=8), target=now + timedelta(hours=2))
        self._run([t])
        self.assertEqual(t.sla_status, "warning")

    def test_never_downgrade(self):
        now = datetime.now(timezone.utc)
        t = self._ticket(sla_status="breached", created=now - timedelta(minutes=5),
                         target=now + timedelta(hours=10))
        self._run([t])
        self.assertEqual(t.sla_status, "breached")

    def test_resolved_tickets_skipped(self):
        t = self._ticket(status="resolved")
        self._run([t])
        self.assertIsNone(t.sla_status)


class TestNotifications(unittest.TestCase):
    def test_skips_without_url(self):
        import notifications
        with mock.patch.object(notifications, "SLACK_WEBHOOK_URL", ""):
            self.assertFalse(notifications.notify_assignment(1, "t", "high", "Eng"))

    def test_returns_true_on_2xx(self):
        import notifications
        fake_resp = mock.MagicMock()
        fake_resp.__enter__.return_value.status = 200
        with mock.patch.object(notifications, "SLACK_WEBHOOK_URL", "http://hook"), \
             mock.patch("urllib.request.build_opener") as op:
            op.return_value.open.return_value = fake_resp
            self.assertTrue(notifications.notify_assignment(1, "t", "high", "Eng"))

### Task 3: Integration tests for the tickets API (live test DB)

**Files:**
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1 fixtures `client` and `db_session`.
- Produces: endpoint coverage for auth 401, create/list/get/resolve/status/assign, 404s, invalid transition 409, similar-incidents shape.

- [x] **Step 1: Write `tests/test_api.py`**

```python
"""Integration tests against a live tracepulse_test Postgres (pgvector).

RCA/embedding are monkeypatched so no Groq call and no sentence-transformers
model load happens. Requires the docker-compose `db` service running.
"""
import pytest

pytestmark = pytest.mark.integration

TICKET = {"title": "API outage", "description": "5xx spike on /checkout",
          "logs": "ERROR upstream timeout", "system": "payments"}


@pytest.fixture(autouse=True)
def _mock_ai(monkeypatch):
    import embeddings
    import rca
    monkeypatch.setattr(rca, "analyze_ticket", lambda *a: {
        "root_cause": "upstream 500", "evidence": "log line", "issue_area": "api",
        "suggested_resolution": "retry with backoff", "priority": "high",
        "severity": "major", "issue_type": "outage", "team": "platform",
    })
    monkeypatch.setattr(embeddings, "embed_ticket", lambda *_: [0.1] * 384)


def test_create_requires_api_key(client):
    r = client.post("/tickets", json=TICKET, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_create_ticket_pipeline(client):
    r = client.post("/tickets", json=TICKET)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open"
    assert body["priority"] == "high"
    assert body["root_cause"] == "upstream 500"
    assert body["target_resolution_time"] is not None  # SLA clock started


def test_create_rejects_blank_title(client):
    r = client.post("/tickets", json={**TICKET, "title": "   "})
    assert r.status_code == 422


def test_list_and_get(client):
    created = client.post("/tickets", json=TICKET).json()
    listed = client.get("/tickets").json()
    assert any(t["id"] == created["id"] for t in listed)
    detail = client.get(f"/tickets/{created['id']}").json()
    assert detail["similar_incidents"] == []


def test_get_missing_404(client):
    assert client.get("/tickets/99999").status_code == 404


def test_resolve_then_status_machine(client):
    t = client.post("/tickets", json=TICKET).json()
    r = client.patch(f"/tickets/{t['id']}/resolve",
                     json={"resolution_text": "rolled back deploy"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert client.patch(f"/tickets/{t['id']}/status",
                        json={"status": "open"}).status_code == 409

### Task 4: Secrets hygiene (.env.example + history audit + rotation)

**Files:**
- Create: `.env.example`

**Interfaces:**
- Consumes: existing `.env` keys.
- Produces: `.env.example` documenting every env var the app reads; a git-history verdict on prior secret leaks.

- [x] **Step 1: Create `.env.example`** (placeholders only — never real values)

```
# PostgreSQL connection (inside Docker Compose use host "db")
DATABASE_URL=postgresql://postgres:postgres@db:5432/tracepulse
# Groq API key for RCA (https://console.groq.com/keys)
GROQ_API_KEY=gsk_replace_me
# Shared API key required in X-API-Key on every request
TRACEPULSE_API_KEY=generate_a_long_random_hex
# sentence-transformers model used for similarity embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
# Slack incoming webhook for engineer-assignment notifications (optional)
SLACK_WEBHOOK_URL=
# Email ingestion (IMAP). Leave EMAIL_IMAP_HOST empty to disable the poller.
EMAIL_IMAP_HOST=
EMAIL_IMAP_PORT=993
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_FOLDER=INBOX
EMAIL_POLL_SECONDS=60
# Base URL the poller uses to POST tickets back to the API
TRACEPULSE_API_URL=http://localhost:8000
# Comma-separated CORS origins (frontend URLs)
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

- [x] **Step 2: Audit git history for leaked secrets**

Run: `git log --all --diff-filter=A -- .env; git ls-files | Select-String env`
Expected: empty — `.env` was never committed. If it WAS: rotate immediately and record the verdict in the commit message.

- [ ] **Step 3: Rotate exposed local secrets (manual, outside git)**

- Regenerate the Gmail app password (Google Account → Security → App passwords); the current one has been displayed in plaintext during analysis.
- Rotate the Groq key at console.groq.com and update `.env` only (never commit).

- [x] **Step 4: Commit**

```bash
git add .env.example
git commit -m "chore: add .env.example documenting all env vars; secrets stay out of git"
```

---

### Task 5: README.md (setup, env vars, API, run, test, deploy)

**Files:**
- Modify: `README.md` (currently empty)

**Interfaces:**
- Consumes: `.env.example` (Task 4), `DEPLOY.md`, `INTEGRATION.md` (link, don't duplicate).
- Produces: the project's front door for a zero-context reader.

- [x] **Step 1: Write `README.md`**

````markdown
# TracePulse

RCA + similarity-search tool for incident tickets. Ingest a ticket (API, webhook, or
email), get an AI root-cause analysis (Groq `openai/gpt-oss-120b`), automatic triage
(priority/severity/issue type/team), an SLA clock with warning/breach escalation,
engineer assignment with Slack notification, and pgvector-powered search over similar
past incidents.

## Stack

FastAPI · PostgreSQL + pgvector · Alembic · sentence-transformers (`all-MiniLM-L6-v2`)
· Groq (gpt-oss-120b) · React (Vite) dashboard · Docker Compose

## Quickstart

```bash
cp .env.example .env          # fill in GROQ_API_KEY, TRACEPULSE_API_KEY
docker compose up --build     # db :5432, api :8001, frontend :5173
```

Open http://localhost:5173. API docs at http://localhost:8001/docs.

## Configuration

All env vars are documented in `.env.example`. Everything except `DATABASE_URL`,
`GROQ_API_KEY` and `TRACEPULSE_API_KEY` has a sane default; email polling is fully
disabled when `EMAIL_IMAP_HOST` is empty.

## API surface (all require `X-API-Key`)


### Task 6: CORS POST + frontend create-ticket form

**Files:**
- Modify: `app/main.py:96` (allow_methods)
- Modify: `frontend/src/api.js` (add `createTicket`)
- Modify: `frontend/src/App.jsx` (add "New Ticket" form)

**Interfaces:**
- Consumes: `POST /tickets` (201; `TicketCreate`: title/description/logs required, system/severity optional).
- Produces: `createTicket(payload) -> Promise<TicketResponse>` in `frontend/src/api.js`; UI form that creates a ticket and refreshes the list.

- [x] **Step 1: Fix CORS middleware in `app/main.py` line 96**

```python
# before
    allow_methods=["GET", "PATCH"],
# after
    allow_methods=["GET", "POST", "PATCH"],
```

- [x] **Step 2: Add `createTicket` to `frontend/src/api.js`** (after `resolveTicket`)

```javascript
export const createTicket = (payload) =>
  request("/tickets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
```

- [x] **Step 3: Add the form to `frontend/src/App.jsx`**

Add `createTicket` to the import from `./api`, add state inside `App()`:

```jsx
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', logs: '', system: '' })
```

Add the submit handler after `doResolve`:

```jsx
  const doCreate = async (e) => {
    e.preventDefault()
    try {
      const t = await createTicket({
        title: form.title, description: form.description,
        logs: form.logs, system: form.system || null,
      })
      setActionMsg(`Created #${t.id}`)
      setForm({ title: '', description: '', logs: '', system: '' })
      setShowForm(false)
      await refreshList()
      selectTicket(t.id)
    } catch (err) {
      setError(`Create failed: ${err.message}`)
    }
  }
```

In the tickets-list section header row, add a toggle button:

```jsx
  <button onClick={() => setShowForm((v) => !v)}>
    {showForm ? 'Cancel' : '+ New Ticket'}
  </button>
```

And just below it, when `showForm` is true:

```jsx
  {showForm && (
    <form className="new-ticket" onSubmit={doCreate}>
      <input required placeholder="Title" value={form.title}
             onChange={(e) => setForm({ ...form, title: e.target.value })} />
      <textarea required placeholder="Description" rows={2} value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
      <textarea required placeholder="Logs" rows={3} value={form.logs}
                onChange={(e) => setForm({ ...form, logs: e.target.value })} />

### Task 7: Alembic as schema source of truth (drop `create_all`)

**Files:**
- Modify: `app/main.py:49` (remove `Base.metadata.create_all`)
- Create: `app/start.sh`
- Modify: `app/Dockerfile` (use `start.sh` as CMD)

**Interfaces:**
- Consumes: existing Alembic migrations in `migrations/versions/` (head: `d4e5f6a7b8c9`).
- Produces: schema changes only via Alembic, in dev AND prod.

- [x] **Step 1: Verify migrations match models on a fresh DB**

Run: `docker compose up -d db`, then `docker compose exec db createdb -U postgres alembic_check`, then
`DATABASE_URL=postgresql://postgres:postgres@localhost:5432/alembic_check .venv\Scripts\python -m alembic upgrade head`
Expected: upgrades cleanly. If a model column is missing from migrations, STOP: generate a migration covering the drift (`alembic revision --autogenerate` against the fresh DB, then hand-review it — do not trust autogenerate blindly), commit that first, then continue.

- [x] **Step 2: Remove `create_all` from `app/main.py`**

Delete line 49 (`Base.metadata.create_all(bind=engine)`) and the now-unused `from models import Base` import (keep `from database import engine` — `_ensure_pgvector()` stays).

- [x] **Step 3: Run migrations at container start**

Create `app/start.sh`:

```sh
#!/bin/sh
set -e
echo "Running Alembic migrations..."
alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

In `app/Dockerfile`, ensure `alembic.ini` and `migrations/` are COPY'd into the image, then replace the current `CMD` with:

```dockerfile
COPY --chmod=755 start.sh /start.sh
CMD ["/start.sh"]
```

(First verify the current CMD/entrypoint in `app/Dockerfile` — if it uses a start script already, insert `alembic upgrade head` at its top instead of adding a new file.)

- [x] **Step 4: Verify the fresh-deploy path end to end**

Run: `docker compose down`, `docker volume rm tracepulse_pgdata`, `docker compose up --build`
Expected: API boots after migrations; `POST /tickets` works; `docker compose exec db psql -U postgres -d tracepulse -c "select * from alembic_version"` shows head `d4e5f6a7b8c9`.

- [x] **Step 5: Full test suite + commit**

```bash
.venv\Scripts\python -m pytest tests -q
git add app/main.py app/start.sh app/Dockerfile
git commit -m "feat: Alembic is the schema source of truth — drop create_all, migrate on container start"
```

---

### Task 8: Docker healthchecks + DB startup race

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml` (same changes)

**Interfaces:**
- Consumes: `db` service name from Task 7's start script (migrations run before uvicorn, so once the API is healthy the schema is ready).
- Produces: `depends_on: condition: service_healthy` for db→api→frontend; `/health` used as API healthcheck.

- [x] **Step 1: Add `/health` endpoint to `app/main.py`** (if absent — check first)

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

- [x] **Step 2: Update `docker-compose.yml`**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: tracepulse
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d tracepulse"]
      interval: 5s
      timeout: 3s
      retries: 12

  api:
    build: ./app
    restart: unless-stopped
    ports:
      - "8001:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8000/health')\""]

### Task 9: Repo hygiene — commit untracked docs/scripts, delete scratch file

**Files:**
- Commit: `docs/showcase_hld_flowchart.pdf`, `docs/showcase_hld_flowchart.png`, `docs/tracepulse_ard_document.md`, `scripts/generate_ard.py`, `scripts/make_showcase_hld_pdf.py`, `scripts/pdf_to_png.py`, `scripts/validate_ard.py`
- Delete: `test_groq_call.py` (root scratch file)

**Interfaces:** none — repo hygiene only.

- [x] **Step 1: Inspect the untracked files** (`git status --short`) and confirm each is meant for the repo (no secrets embedded — grep for `gsk_`, passwords, hostnames).
- [x] **Step 2: Delete the scratch file**

```bash
Remove-Item test_groq_call.py
```

- [x] **Step 3: Commit**

```bash
git add docs scripts
git commit -m "chore: commit ARD/showcase docs and generator scripts; remove root scratch Groq test file"
```

---

### Task 10: CI — GitHub Actions (pytest unit + integration with pgvector service)

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `requirements-dev.txt`, `pytest.ini`, the `integration` marker, `tests/conftest.py` (reads `DATABASE_URL`).
- Produces: CI running the full suite on every push/PR to `main`.

- [x] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      db:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: tracepulse_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s --health-timeout 3s --health-retries 12
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/tracepulse_test
      TRACEPULSE_API_KEY: test-key
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install deps
        run: |
          pip install -r requirements-dev.txt
          pip install fastapi uvicorn sqlalchemy psycopg2-binary pgvector pydantic \

### Task 11: GET /tickets pagination + filtering

**Files:**
- Modify: `app/routers/tickets.py:78-80` (`list_tickets`)
- Test: `tests/test_api.py` (append)

**Interfaces:**
- Consumes: `Ticket` model columns `status`, `priority`, `sla_status`.
- Produces: `GET /tickets?status=&priority=&sla_status=&limit=&offset=` (defaults limit=100, offset=0, limit cap 500) — backwards compatible (no params → old behavior).

- [x] **Step 1: Failing tests** — append to `tests/test_api.py`:

```python
def test_list_filters_and_pagination(client):
    client.post("/tickets", json=TICKET)
    client.post("/tickets", json={**TICKET, "title": "Low prio"})
    assert len(client.get("/tickets").json()) == 2
    # priority comes from mocked triage = high
    assert client.get("/tickets", params={"priority": "critical"}).json() == []
    assert len(client.get("/tickets", params={"priority": "high"}).json()) == 2
    assert len(client.get("/tickets", params={"limit": 1}).json()) == 1
    assert len(client.get("/tickets", params={"limit": 1, "offset": 1}).json()) == 1
    assert client.get("/tickets", params={"limit": 9999}).status_code == 422


def test_list_filter_by_status(client):
    t = client.post("/tickets", json=TICKET).json()
    assert len(client.get("/tickets", params={"status": "open"}).json()) == 1
    client.patch(f"/tickets/{t['id']}/resolve", json={"resolution_text": "fixed"})
    assert client.get("/tickets", params={"status": "open"}).json() == []
    assert len(client.get("/tickets", params={"status": "resolved"}).json()) == 1
```

Run: `.venv\Scripts\python -m pytest tests/test_api.py -k "filter" -q`
Expected: FAIL (params ignored today).

- [x] **Step 2: Implement in `app/routers/tickets.py`** (replace `list_tickets`; add `from fastapi import Query` to imports)

```python
@router.get("", response_model=list[TicketResponse])
def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    sla_status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _key: None = Depends(verify_api_key),
):
    q = db.query(Ticket)
    if status:
        q = q.filter(Ticket.status == status)
    if priority:
        q = q.filter(Ticket.priority == priority)
    if sla_status:

### Task 12: Email ingest hardening (loop prevention + HTML bodies)

**Files:**
- Modify: `app/email_ingest.py`
- Create: `tests/test_email_units.py`

**Interfaces:**
- Consumes: existing `poll_inbox` flow (subject→title, body→description).
- Produces: `should_skip_subject(subject: str) -> bool` (skip subjects containing `[TracePulse]` — loop guard against our own notification mail landing back in the inbox); `body_text_from_message(msg) -> str` (prefers text/plain, falls back to HTML with tags stripped, stdlib `html.parser` only).

- [x] **Step 1: Failing tests — create `tests/test_email_units.py`**

```python
"""Unit tests for email_ingest helpers (no IMAP, no network)."""
import email as email_lib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


class TestLoopGuard(unittest.TestCase):
    def test_subject_with_tracepulse_tag_skipped(self):
        from email_ingest import should_skip_subject
        self.assertTrue(should_skip_subject("[TracePulse] Ticket #3 assigned"))
        self.assertFalse(should_skip_subject("DB down in prod"))


class TestHtmlExtraction(unittest.TestCase):
    def test_html_body_converted_to_text(self):
        from email_ingest import body_text_from_message
        raw = (
            b"From: a@b.c\r\nSubject: Help\r\nMIME-Version: 1.0\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n\r\n"
            b"<html><body><p>Disk is <b>full</b> on /var</p></body></html>"
        )
        msg = email_lib.message_from_bytes(raw)
        self.assertIn("Disk is full on /var", body_text_from_message(msg))

    def test_plain_body_passthrough(self):
        from email_ingest import body_text_from_message
        raw = (
            b"From: a@b.c\r\nSubject: Help\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\njust text"
        )
        msg = email_lib.message_from_bytes(raw)
        self.assertEqual(body_text_from_message(msg), "just text")


if __name__ == "__main__":
    unittest.main()
```

Run: `.venv\Scripts\python -m pytest tests/test_email_units.py -q`
Expected: FAIL — helpers don't exist yet.

- [x] **Step 2: Implement in `app/email_ingest.py`**

```python
from html.parser import HTMLParser

LOOP_SUBJECT_TAG = "[TracePulse]"


class _HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data):
        self._chunks.append(data)

    def text(self) -> str:
        return " ".join("".join(self._chunks).split())


def body_text_from_message(msg) -> str:
    """Plain text from email.message.Message: prefers text/plain,
    falls back to HTML with tags stripped. Whitespace-normalized."""
    if msg.is_multipart():
        plain = html = None
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_payload(decode=True)
            elif ctype == "text/html" and html is None:
                html = part.get_payload(decode=True)
        payload = plain if plain is not None else html
        ctype = "text/plain" if plain is not None else "text/html"
    else:
        payload = msg.get_payload(decode=True)

### Task 13: SLA warning/breach Slack notifications

**Files:**
- Modify: `app/notifications.py` (new `notify_sla` + shared `_post_slack` helper)
- Modify: `app/sla.py` (`_check_slas_inner` transition block)
- Test: `tests/test_units.py` (append `TestSlaNotify`)

**Interfaces:**
- Consumes: `notify_assignment`'s fail-safe pattern (return bool, never raise).
- Produces: `notifications.notify_sla(ticket_id: int, title: str, sla_status: str, engineer_name: str | None = None) -> bool`; each newly-flagged SLA transition fires one Slack message. `notify_assignment`'s public signature stays unchanged.

- [x] **Step 1: Failing test** — append to `tests/test_units.py`:

```python
class TestSlaNotify(unittest.TestCase):
    def test_notify_sla_called_on_transition(self):
        import sla
        now = datetime.now(timezone.utc)
        t = mock.Mock()
        t.id = 7
        t.title = "DB down"
        t.sla_status = None
        t.status = "open"
        t.created_at = now - timedelta(hours=9)
        t.target_resolution_time = now + timedelta(hours=1)
        t.assigned_engineer_id = 1
        eng = mock.Mock()
        eng.name = "Dana"
        with mock.patch("sla.SessionLocal") as s, mock.patch("sla.or_", lambda *a: True), \
             mock.patch("sla.notify_sla") as ns:
            s.return_value.query.return_value.filter.return_value.filter.return_value \
                .all.return_value = [t]
            s.return_value.query.return_value.filter.return_value.first.return_value = eng
            sla.check_slas()
        ns.assert_called_once_with(7, "DB down", "warning", "Dana")
```

Run: `.venv\Scripts\python -m pytest tests/test_units.py::TestSlaNotify -q`
Expected: FAIL (`notify_sla` not used in sla yet).

- [x] **Step 2: Refactor `app/notifications.py`** — extract the POST into `_post_slack(text: str) -> bool` (same body/headers/opener/timeout/exception handling as `notify_assignment` today; `notify_assignment` becomes `return _post_slack(text)` with its signature and fail-safe behavior unchanged). Then add:

```python
def notify_sla(ticket_id: int, title: str, sla_status: str, engineer_name: str | None = None) -> bool:
    """Notify on SLA warning/breach. Fail-safe like notify_assignment."""
    who = f" (assigned: {engineer_name})" if engineer_name else ""
    emoji = ":rotating_light:" if sla_status == "breached" else ":warning:"
    return _post_slack(
        f"{emoji} SLA {sla_status.upper()} — ticket #{ticket_id}{who}\n*{title}*"
    )
```

- [x] **Step 3: Wire it into `app/sla.py`**

Add imports `from models import Engineer` and `from notifications import notify_sla`. Inside `_check_slas_inner`, after `ticket.sla_status = new_status` (before `session.commit()`), add:

```python
            engineer = None
            if ticket.assigned_engineer_id:
                engineer = (
                    session.query(Engineer)
                    .filter(Engineer.id == ticket.assigned_engineer_id)
                    .first()
                )
            notify_sla(
                ticket.id, ticket.title, new_status,
                engineer.name if engineer else None,
            )
```

(Safe in tests/CI: `SLACK_WEBHOOK_URL` is unset there, and the test mocks `notify_sla` anyway.)

- [x] **Step 4: Run full suite + commit**

```bash
.venv\Scripts\python -m pytest tests -q
git add app/sla.py app/notifications.py tests/test_units.py
git commit -m "feat: Slack notifications on SLA warning/breach transitions"
```

---

## Self-Review

1. **Spec coverage** — P0: tests (Tasks 1–3), secrets hygiene (4), README (5). P1: frontend create-ticket + CORS (6), Alembic source of truth (7), healthchecks/startup race (8), untracked docs (9). P2: CI (10), pagination/filtering (11), email hardening (12), SLA notifications (13). Every gap from the analysis has a task; deliberate deferrals listed below.
2. **Placeholder scan** — all code steps contain complete code; verification steps state exact commands and expected results. No TBDs.
3. **Type consistency** — `notify_sla(ticket_id, title, sla_status, engineer_name=None)` defined in Task 13 Step 2, used identically in Step 3 and the test. Fixture names `client`/`db_session` consistent between Task 1 conftest and consumers (Tasks 3, 11). Env var names in `.env.example` (Task 4) match those read in `app/main.py`, `app/email_ingest.py`, `app/auth.py`.

## Deliberately deferred (post-v1 backlog)

- Per-user auth/roles + rate limiting (static shared API key is demo-grade)
- Proxy-injected `X-API-Key` so the browser bundle stops exposing the key
- Frontend pagination controls over Task 11's API; engineer management UI
- Production frontend build in the dev compose (replace Vite dev-server container)
- Dedicated scheduler worker (in-process jobs duplicate if API scales past 1 replica)
- Metrics / error tracking (Sentry or Prometheus)
- Email ingest attachments, per-sender dedup beyond the loop guard

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-01-tracepulse-completion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task and review between tasks.

**2. Inline Execution** — I execute tasks in this session using executing-plans, batched with checkpoints.

**Which approach?**

        ctype = msg.get_content_type()
    if payload is None:
        return ""
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    if ctype == "text/html":
        parser = _HTMLToText()
        parser.feed(text)
        return parser.text()
    return text.strip()


def should_skip_subject(subject: str) -> bool:
    """Skip our own notification mail so ingest never loops on itself."""
    return LOOP_SUBJECT_TAG in (subject or "")
```

Then in the existing message-processing loop: decode the subject (collapsing CRLF-wrapped subjects as already fixed on `main`), call `should_skip_subject` and `continue` before creating a ticket, and use `body_text_from_message(msg)` instead of the current body-extraction code.

- [x] **Step 3: Run existing email tests too**

Run: `.venv\Scripts\python -m pytest tests -q`
Expected: all PASS, including the pre-existing `tests/test_email_ingest.py`.

- [x] **Step 4: Commit**

```bash
git add app/email_ingest.py tests/test_email_units.py
git commit -m "feat: email ingest hardening — [TracePulse] loop guard, HTML body to text"
```

---

        q = q.filter(Ticket.sla_status == sla_status)
    return q.order_by(Ticket.id.desc()).offset(offset).limit(limit).all()
```

- [x] **Step 3: Run full suite, then commit**

```bash
.venv\Scripts\python -m pytest tests -q
git add app/routers/tickets.py tests/test_api.py
git commit -m "feat: GET /tickets pagination + status/priority/sla_status filters"
```

---

            openai apscheduler
      - name: Run tests
        run: python -m pytest tests -q
```

Note: CI intentionally does NOT install `torch`/`sentence-transformers` (huge, and embeddings are mocked in tests). If `app/embeddings.py` imports `sentence_transformers` at module import time and test collection breaks, make that import lazy (load the model inside `embed_ticket`) and commit that guard as part of this task.

- [ ] **Step 2: Push and watch the run**

Run: `git push`, then check the Actions tab.
Expected: green run covering unit + integration tests.

- [x] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions running full pytest suite with pgvector service"
```

---

      interval: 10s
      timeout: 5s
      retries: 6

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "5173:5173"
    env_file:
      - ./frontend/.env
    depends_on:
      api:
        condition: service_healthy

volumes:
  pgdata:
```

Mirror the same healthcheck/depends_on changes into `docker-compose.prod.yml` (keep its Caddy service; make it depend on api with `condition: service_healthy`).

- [x] **Step 3: Verify**

Run: `docker compose down && docker compose up --build`
Expected: db becomes healthy before api starts; `docker compose ps` shows `(healthy)` for db and api.

- [x] **Step 4: Commit**

```bash
git add app/main.py docker-compose.yml docker-compose.prod.yml
git commit -m "feat: add /health + healthchecks and startup ordering in compose files"
```

---

      <input placeholder="System (optional)" value={form.system}
             onChange={(e) => setForm({ ...form, system: e.target.value })} />
      <button className="primary" type="submit">Create</button>
    </form>
  )}
```

- [x] **Step 4: Manual smoke test**

Run: `docker compose up --build`, open http://localhost:5173, create a ticket.
Expected: ticket appears in the list with AI RCA + SLA target filled in.

- [x] **Step 5: Run full test suite and commit**

```bash
.venv\Scripts\python -m pytest tests -q
git add app/main.py frontend/src/api.js frontend/src/App.jsx
git commit -m "feat: frontend create-ticket form; allow POST in CORS middleware"
```

---

| Method | Path | Purpose |
|---|---|---|
| POST | `/tickets` | Create ticket (runs RCA → triage → embedding → SLA) |
| GET | `/tickets` | List tickets |
| GET | `/tickets/{id}` | Detail incl. embedding + similar incidents |
| PATCH | `/tickets/{id}/status` | State machine: open/in_progress/resolved/closed |
| PATCH | `/tickets/{id}/resolve` | Resolve with resolution text |
| PATCH | `/tickets/{id}/assign` | Assign engineer (+ Slack notify) |
| GET | `/engineers` | Active engineers (assignment dropdown) |
| POST | `/ingest/webhook` | PulseGrid chain ingest with dedup |

## Tests

```bash
pip install -r requirements-dev.txt
docker compose up -d db                # integration tests need a live pgvector DB
python -m pytest tests -q              # unit tests run anywhere; integration auto-skip w/o DB
```

## Docs

- Deployment (Railway / Oracle VM): [DEPLOY.md](DEPLOY.md)
- PulseGrid integration: [INTEGRATION.md](INTEGRATION.md)
````

- [x] **Step 2: Sanity-check every claim against the code** (ports 8001/5173, endpoint paths in `app/routers/*.py`, status codes). Fix the README if any claim is wrong — never weaken a test to match a doc.

- [x] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: write README (quickstart, config, API surface, tests)"
```

---

    assert client.patch(f"/tickets/{t['id']}/status",
                        json={"status": "in_progress"}).status_code == 200


def test_assign_flow(client, db_session):
    from models import Engineer
    eng = Engineer(name="Dana Ops", email="d@x.io", slack_handle="@d", active=True)
    db_session.add(eng)
    db_session.commit()
    t = client.post("/tickets", json=TICKET).json()
    r = client.patch(f"/tickets/{t['id']}/assign", json={"engineer_id": eng.id})
    assert r.status_code == 200 and r.json()["assigned_engineer_id"] == eng.id
    assert client.patch(f"/tickets/{t['id']}/assign",
                        json={"engineer_id": 99999}).status_code == 404
```

- [x] **Step 2: Start the dev DB if not running, then run tests**

Run: `docker compose up -d db` then `.venv\Scripts\python -m pytest tests -q`
Expected: all PASS (unit + integration).

- [x] **Step 3: Commit**

```bash
git add tests/test_api.py
git commit -m "test: integration coverage for tickets API (auth, CRUD, resolve, status machine, assign)"
```

---


    def test_fail_safe_on_network_error(self):
        import urllib.error
        import notifications
        with mock.patch.object(notifications, "SLACK_WEBHOOK_URL", "http://hook"), \
             mock.patch("urllib.request.build_opener") as op:
            op.return_value.open.side_effect = urllib.error.URLError("down")
            self.assertFalse(notifications.notify_assignment(1, "t", "high", "Eng"))


if __name__ == "__main__":
    unittest.main()
```

The mocked SLA tests patch `sla.SessionLocal` and `sla.or_` so the `_check_slas_inner` query chain (`.filter(...).filter(...).all()`) is fully mocked without a real DB.

- [x] **Step 3: Run and verify all pass**

Run: `.venv\Scripts\python -m pytest tests/test_units.py -q`
Expected: all PASS.

- [x] **Step 4: Commit**

```bash
git add tests/test_units.py
git commit -m "test: unit coverage for auth, schemas, RCA parsing, SLA logic, Slack notifications"
```

---

    def test_create_strips_whitespace(self):
        from schemas import TicketCreate
        t = TicketCreate(title="  DB down  ", description=" x ", logs=" y ")
        self.assertEqual(t.title, "DB down")

    def test_create_rejects_blank(self):
        from pydantic import ValidationError
        from schemas import TicketCreate
        with self.assertRaises(ValidationError):
            TicketCreate(title="   ", description="x", logs="y")

    def test_closed_is_terminal(self):
        from schemas import ALLOWED_TRANSITIONS
        self.assertNotIn("open", ALLOWED_TRANSITIONS["closed"])
        self.assertIn("in_progress", ALLOWED_TRANSITIONS["resolved"])
```

def db_session(db_engine):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
    with db_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE tickets, engineers, ingest_dedup RESTART IDENTITY CASCADE"
        ))


@pytest.fixture
def client(db_session):
    from database import get_db
    from main import app
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db_session
    # No `with` block: lifespan (scheduler jobs) deliberately skipped in tests.
    yield TestClient(app, headers={"X-API-Key": "test-key"})
    app.dependency_overrides.clear()
```

- [x] **Step 5: Verify pytest runs the existing suite**

Run: `.venv\Scripts\python -m pytest tests -q`
Expected: existing tests pass; integration-marked tests skip if no local DB.

- [x] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/conftest.py
git commit -m "test: add pytest infra — conftest with live test-DB fixtures, integration marker, API client"
```

---
