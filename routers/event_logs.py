# routers/event_logs.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from auth.deps import get_current_user
from schemas.event_log import EventLogCreate, EventLogResponse
from models.event_log import EventLog
from typing import List

router = APIRouter(
    prefix="/event_logs",
    tags=["Event Logs"]
)

@router.post("/", response_model=EventLogResponse)
def create_event_log(
    data: EventLogCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    log = EventLog(
        user_id=user.user_id,
        task_id=data.task_id,
        event_type=data.event_type,
        data=data.data,
        device=data.device
    )

    db.add(log)
    db.commit()
    db.refresh(log)
    return log

@router.get("/", response_model=List[EventLogResponse])
def get_event_logs(
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    logs = db.query(EventLog).filter(EventLog.user_id == user.user_id).all()
    return logs