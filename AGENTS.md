# TracePulse

RCA + similarity-search tool for incident tickets. Standalone, no dep on Pulsegrid/LogPulse.

Stack: FastAPI, PostgreSQL+pgvector, Alembic, Groq (openai/gpt-oss-120b), sentence-transformers, Docker Compose.

Build order: see SPECS.md. Work one item at a time, tick box, commit.
Rule: never hand-patch a mistake. If output wrong, fix the instruction, redo.
