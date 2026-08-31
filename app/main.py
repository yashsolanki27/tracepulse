import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Frontend origins (Phase 2d). Env-configurable for Railway (comma-separated
# CORS_ORIGINS); defaults to the local Vite dev server.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

from database import engine
from email_ingest import poll_inbox
from models import Base
from routers import engineers, ingest, tickets
from sla import check_slas


def _ensure_pgvector() -> None:
    """Create the vector extension if missing (Railway pgvector template)."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception:
        logging.getLogger("tracepulse.db").warning(
            "Could not CREATE EXTENSION vector (may already exist or be managed externally)",
            exc_info=True,
        )


_ensure_pgvector()
Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Run immediately at startup, then every 5 minutes. BackgroundScheduler runs
    # jobs in worker threads, so app startup is never blocked.
    scheduler.add_job(
        check_slas,
        "interval",
        seconds=300,
        id="sla_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()

    # Phase 2e: email ingestion poller. Only scheduled when an inbox is
    # configured; otherwise the API runs exactly as before.
    if os.getenv("EMAIL_IMAP_HOST"):
        scheduler.add_job(
            poll_inbox,
            "interval",
            seconds=int(os.getenv("EMAIL_POLL_SECONDS", "60")),
            id="email_poll",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            next_run_time=datetime.now(timezone.utc),
        )
        logging.getLogger("tracepulse.email").info(
            "Email ingestion enabled: host=%s folder=%s",
            os.getenv("EMAIL_IMAP_HOST"), os.getenv("EMAIL_FOLDER", "INBOX"),
        )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="TracePulse", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "PATCH"],
    allow_headers=["X-API-Key", "Content-Type"],
)
app.include_router(tickets.router)
app.include_router(engineers.router)
app.include_router(ingest.router)
