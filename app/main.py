import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from database import engine
from models import Base
from routers import tickets
from sla import check_slas

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
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="TracePulse", version="0.1.0", lifespan=lifespan)
app.include_router(tickets.router)
