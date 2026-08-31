from fastapi import FastAPI

from database import engine
from models import Base
from routers import tickets

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TracePulse", version="0.1.0")
app.include_router(tickets.router)
