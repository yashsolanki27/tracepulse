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

## API surface (all endpoints require the `X-API-Key` header)

| Method | Path                      | Purpose                                    |
|--------|---------------------------|--------------------------------------------|
| POST   | `/tickets`                | Create ticket (runs full RCA pipeline)     |
| GET    | `/tickets`                | List all tickets                           |
| GET    | `/tickets/{id}`           | Ticket detail + similar past incidents     |
| PATCH  | `/tickets/{id}/status`    | Transition status (validated transitions)  |
| PATCH  | `/tickets/{id}/resolve`   | Resolve with resolution text               |
| PATCH  | `/tickets/{id}/assign`    | Assign engineer (sends Slack notification) |
| GET    | `/engineers`              | List active engineers (assign dropdown)    |
| POST   | `/ingest/webhook`         | PulseGrid chain ingest (201/202 dedup)     |

## Tests

```bash
pip install -r requirements-dev.txt
docker compose up -d db                # integration tests need a live pgvector DB
python -m pytest tests -q              # unit tests run anywhere; integration auto-skip w/o DB
```

## Docs

- Deployment (Oracle Cloud VM, Docker Compose + Caddy): [DEPLOY.md](DEPLOY.md)
- PulseGrid integration (chain ingest via LogPulse): [INTEGRATION.md](INTEGRATION.md)

