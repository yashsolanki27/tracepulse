from fastapi import FastAPI

from app.database import engine
from app.models import Base
from app.routers import tickets

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TracePulse", version="0.1.0")
app.include_router(tickets.router)
