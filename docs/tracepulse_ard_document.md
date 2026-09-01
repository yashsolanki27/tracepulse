# TracePulse — ARD (Application Requirements & Design Document)

> **Purpose:** Single source of truth for presentations. Each numbered section maps 1:1 to a PPT slide. Project: **TracePulse** — AI-powered Root Cause Analysis & Similarity Search engine for incident tickets.
>
> Repo: https://github.com/yashsolanki27/tracepulse · Version: 0.1.0 · Status: V1 + V2 shipped (SPECS.md all ticks complete)

---

## 1. Title Slide / Project Overview

| Field | Value |
|---|---|
| Project Name | TracePulse |
| Tagline | "From incident to resolution — AI-powered RCA, similarity search & SLA management" |
| Category | Standalone incident-management microservice (no dependency on Pulsegrid/LogPulse) |
| Core Problem | Ops teams manually write RCAs, can't find past similar incidents, miss SLA deadlines, mis-route tickets |
| Core Solution | One API that auto-analyzes (LLM RCA), auto-triages, finds similar past tickets via vector search, enforces SLA clocks, and assigns engineers |
| Current Version | V1 (RCA + similarity) + V2 (triage, SLA, assignment, notifications, frontend, email ingest, webhook chain) — all complete |

---

## 2. Problem Statement

1. **Manual RCA is slow** — engineers write root-cause analysis by hand for every incident.
2. **No institutional memory** — past similar incidents and their fixes are never surfaced.
3. **Inconsistent triage** — priority/severity/team classification depends on who reads the ticket.
4. **SLA breaches go unnoticed** — no proactive tracking of resolution deadlines.
5. **Alerts flood in from multiple sources** (Alertmanager, cron jobs, email) with duplicates.

## 3. Proposed Solution

- **AI Root Cause Analysis:** Groq LLM (`openai/gpt-oss-120b`) generates root cause, evidence, issue area, and suggested resolution from ticket title/description/logs.
- **Similarity Search:** Sentence-transformers embeddings (384-dim) in PostgreSQL `pgvector`; cosine similarity surfaces top-K similar past tickets.
- **Auto Triage:** LLM classifies priority, severity, issue type, and suggested owning team at creation.
- **SLA Engine:** Deadline computed at creation; scheduled job (every 5 min) flags `warning`/`breached`.
- **Assignment & Notifications:** Tickets assigned to engineers; Slack webhook notifies assignee.
- **Multi-source Ingestion:** IMAP email polling + `POST /ingest/webhook` for external producers (PulseGrid chain) with dedup.

## 4. Objectives (Measurable)

| # | Objective | Target |
|---|---|---|
| O1 | RCA generated automatically | ≤ 10s per ticket, retry once, `null` on failure (never blocks creation) |
| O2 | Similar incidents found | Top-K matches with cosine similarity in a single API response |
| O3 | SLA monitoring | Scheduled check every 5 min; statuses: `warning` / `breached` |
| O4 | Duplicate incidents | `dedup_key` cooldown window (default 24h) → `202 deduplicated` |
| O5 | Security | API-key auth (`X-API-Key`) on every endpoint |

## 5. Scope

**In scope (V1):** repo scaffold + Docker Compose + DB, tickets table with pgvector, CRUD + validation, API-key auth, RCA wiring, similarity search, resolve endpoint, seed script, E2E test ship gate.

**In scope (V2):**
- **2a:** AI triage (priority/severity/issue type/team); full resolve/close workflow (`open / in_progress / resolved / closed`).
- **2b:** SLA clock + deadline; scheduled SLA monitoring & escalation.
- **2c:** Engineers table + assignment; Slack webhook notifications.
- **2d:** React (Vite) frontend; unified dashboard view (SLA/RCA/AI/similar/actions).
- **2e:** IMAP email ingestion → auto-creates tickets through the same pipeline.

**Out of scope:** real-time log streaming, multi-tenancy, RBAC/SSO, mobile app, non-Postgres vector stores.

## 6. Technology Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python ≥ 3.13), Uvicorn |
| Database | PostgreSQL + **pgvector** extension |
| ORM / Migrations | SQLAlchemy 2.0, Alembic (5 migrations shipped) |
| LLM (RCA + triage) | Groq API — model `openai/gpt-oss-120b` (OpenAI SDK) |
| Embeddings | sentence-transformers → 384-dim vectors |
| Scheduling | APScheduler: SLA check every 300s, email poll every 60s |
| Email ingestion | Python stdlib `imaplib` (IMAP4_SSL) |
| Notifications | Slack incoming webhook |
| Frontend | React + Vite, served by Caddy in production |
| Validation | Pydantic v2 |
| Testing | pytest / unittest (18 tests passing, incl. 9 ingest tests) |
| Deployment | Docker / Docker Compose (dev + prod), Railway-ready deploy scripts |

## 7. High-Level Architecture

```
Sources                      TracePulse API (FastAPI)                     Output
────────                     ───────────────────────                      ──────
PulseGrid webhooks  ──┐
Reconciliation jobs  ─┼─►  POST /ingest/webhook ─┐
IMAP email poller    ─┘                         │
                                POST /tickets ──┤
                                                ▼
                          ┌─────────────────────────────────────┐
                          │        Ticket Pipeline              │
                          │ 1. Validate (Pydantic)              │
                          │ 2. Groq RCA (root cause, evidence,  │
                          │    resolution) — 10s timeout        │
                          │ 3. Groq Triage (priority, severity, │
                          │    issue type, team)                │
                          │ 4. Embedding (384-d) → pgvector     │
                          │ 5. SLA deadline computed            │
                          │ 6. Auto-assign engineer + Slack     │
                          └─────────────────────────────────────┘
                                                │
        Scheduled jobs (APScheduler)            ▼
        - SLA check every 5 min ───► flag warning/breach
        - Email poll every 60s  ───► unseen mail → new ticket
                                                │
                        React Dashboard  ◄──────┘   GET endpoints
                        (unified ticket view)
```

**Chain-mode integration (fixed order):** `Alertmanager / reconciliation-job / Newman → LogPulse /triage → TracePulse /ingest/webhook`. LogPulse classifies; TracePulse manages the incident (RCA, similarity, SLA, assignment). If TracePulse fails, producer dedup state is NOT updated, so the next run retries.

## 8. Data Model

### 8.1 `tickets`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | auto-increment |
| title, description, logs | String / Text (required) | logs = raw error text |
| system | String | affected system |
| severity | String | manual severity |
| created_at | DateTime(tz) | UTC default |
| root_cause / evidence / issue_area / suggested_resolution | Text | AI RCA output |
| priority | String | AI triage: low / medium / high / critical |
| ai_severity | String | AI triage (separate from manual) |
| issue_type | String | bug / outage / config / performance |
| team | String | suggested owning team |
| status | String | open / in_progress / resolved / closed |
| target_resolution_time | DateTime(tz) | SLA deadline |
| sla_status | String | null / warning / breached |
| assigned_engineer_id | FK → engineers.id | |
| resolution_text, resolved_at | Text / DateTime | set on resolve |
| embedding | Vector(384) | pgvector similarity search |

### 8.2 `engineers`
id (PK), name (required), email, slack_handle, active (bool, default true).

### 8.3 `ingest_dedup`
dedup_key (PK, e.g. `alert:{alertname}:{instance}`), last_reported_at, ticket_id, source. Key seen within cooldown → `202`, no new ticket.

**Alembic migrations:** create tickets → add triage + status → add SLA fields → add engineers + assignment → replace seed engineers.

## 9. API Endpoints

| Method & Path | Purpose |
|---|---|
| `POST /tickets` | Create ticket → full pipeline (RCA → triage → embedding → SLA → assignment) |
| `GET /tickets` / `GET /tickets/{id}` | List / detail incl. RCA, similar incidents, SLA status |
| `PATCH /tickets/{id}` | Update (status workflow, assignment, resolution) |
| `POST /tickets/{id}/resolve` | Resolve with resolution text |
| `POST /tickets/{id}/similar` | Similarity search over past tickets |
| `/engineers` router | Engineer CRUD & assignment |
| `POST /ingest/webhook` | External ingestion (chain mode). **201 created / 202 deduplicated / 401 bad key / 422 bad payload** |

**Auth:** `X-API-Key` header on every request. **CORS:** restricted origins via `CORS_ORIGINS`, methods GET/PATCH only.

**Webhook payload example:**
```json
{
  "source": "alertmanager",
  "title": "HighMemoryUsage on app-1",
  "description": "...", "logs": "...",
  "labels": {"alertname": "HighMemoryUsage", "instance": "app-1"},
  "dedup_key": "alert:HighMemoryUsage:app-1",
  "triage": {"triage_id": "tp_991", "category": "integration", "confidence": 0.92}
}
```

## 10. Key Workflows

1. **Ticket creation pipeline:** validate → RCA (Groq, 10s timeout, retry once, null-on-fail + logging) → AI triage → embed & store vector → SLA deadline → auto-assign → Slack notify → respond.
2. **SLA monitoring:** APScheduler every 5 min flags tickets nearing deadline (`warning`) or past deadline (`breached`).
3. **Email ingestion:** IMAP poll every 60s → unseen mail → subject = title, body = description → internal POST `/tickets` → mark seen. Disabled when `EMAIL_IMAP_HOST` unset.
4. **Resolve/close:** engineer sets `resolution_text` → status `resolved` → ticket becomes searchable context for future similarity matches.
5. **Chain ingestion:** webhook → dedup check → `201` full pipeline / `202` deduplicated.

## 11. Configuration (Environment Variables)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection |
| `GROQ_API_KEY` | LLM access (RCA + triage) |
| `TRACEPULSE_API_KEY` | API-key auth for all endpoints |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `INGEST_DEDUP_HOURS` | Dedup cooldown (default 24) |
| `EMAIL_IMAP_HOST` / `EMAIL_IMAP_PORT` (993) / `EMAIL_USER` / `EMAIL_PASSWORD` / `EMAIL_FOLDER` (INBOX) / `EMAIL_POLL_SECONDS` (60) | Email ingestion |
| `TRACEPULSE_API_URL` | Where the email poller posts tickets |

## 12. Non-Functional Requirements

- **Reliability:** RCA failure never blocks ticket creation (null-on-fail, logged). Scheduler uses `max_instances=1`, `coalesce`, `misfire_grace_time=60`.
- **Performance:** RCA bounded at 10s timeout; similarity is a single indexed vector query.
- **Security:** API-key auth everywhere; CORS allow-list; credentials in env only.
- **Maintainability:** Alembic migrations, modular routers, prompt versioned in `app/prompts/rca_v1.txt`.
- **Portability:** Docker Compose (dev + prod), Railway deployment scripts, auto `CREATE EXTENSION vector` at startup.

## 13. Testing & Verification

- **18 tests passing** (`uv run --with pytest pytest tests`) including 9 ingest-webhook tests + email ingest tests.
- **Live chain simulation (2026-08-31):** ingest with `dedup_key=order:77` → ticket #40 created with RCA set, `priority=high`, 5 similar incidents, SLA +8h; repeat call → `202 deduplicated`; missing key → `401`.
- Seed & verification scripts: `scripts/seed.py`, `verify_ranking.py`, `chain_test.py`, `check_ingest.py`, `backfill_embeddings.py`.

## 14. Future Enhancements

1. Complete React UI polish (scaffold, API wiring, dashboard done).
2. RCA feedback loop — engineer corrections refine prompts.
3. Connectors: Jira, PagerDuty, ServiceNow.
4. Auto-assignment by team + workload balancing.
5. Analytics: MTTR, SLA compliance trends.
6. RBAC / user roles beyond API keys.

## 15. Suggested PPT Slide Mapping

| Slide | Content |
|---|---|
| 1 | Title + tagline (§1) |
| 2 | Problem statement (§2) |
| 3 | Solution overview (§3) |
| 4 | Objectives (§4) |
| 5 | Tech stack (§6) |
| 6 | Architecture diagram (§7) |
| 7 | Data model (§8) |
| 8 | API endpoints (§9) |
| 9 | Key workflows (§10) |
| 10 | Integrations / chain mode (§7) |
| 11 | Testing & verification (§13) |
| 12 | Scope & future work (§5, §14) |
| 13 | Demo / Q&A |

