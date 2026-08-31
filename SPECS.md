# TracePulse V1 Build Order

- [x] 1. Scaffold repo/compose/DB connection
- [x] 2. Tickets table + pgvector + Alembic init
- [x] 3. Plain CRUD + input validation
- [x] 4. API key auth
- [x] 5. Wire RCA (gpt-oss-120b, 10s timeout, retry once, null-on-fail, logging)
- [x] 6. Wire similarity search
- [x] 7. Resolve endpoint
- [x] 8. Seed script, verify matches
- [x] 9. End-to-end test — ship gate

# V2 Build Order

## Phase 2a (no blockers)

- [x] Incident triage — auto-classify priority, severity, issue type, team
- [x] Full resolve/close workflow — status field (open/in_progress/resolved/closed)

## Phase 2b

- [x] SLA clock: start SLA clock + deadline on ticket creation
- [x] SLA monitoring & escalation: scheduled job checks tickets nearing/breaching deadline, flags status

## Phase 2c

- [x] Engineer assignment: new engineer/user table, assign ticket to engineer
- [x] Notification: notify assigned engineer via Slack webhook

