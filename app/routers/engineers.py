"""Engineer lookup endpoints (used by the frontend for the Assign dropdown)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import verify_api_key
from database import get_db
from models import Engineer
from schemas import EngineerResponse

router = APIRouter(prefix="/engineers", tags=["engineers"])


@router.get("", response_model=list[EngineerResponse])
def list_engineers(_key: None = Depends(verify_api_key), db: Session = Depends(get_db)):
    return db.query(Engineer).filter(Engineer.active.is_(True)).order_by(Engineer.name).all()