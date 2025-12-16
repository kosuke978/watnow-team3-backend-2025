# schemas/event_log.py
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime
from uuid import UUID

class EventLogCreate(BaseModel):
    task_id: Optional[UUID] = None
    event_type: str
    data: Optional[Dict] = None
    device: Optional[str] = None

class EventLogResponse(BaseModel):
    log_id: UUID
    user_id: UUID
    task_id: Optional[UUID]
    event_type: str
    data: Optional[Dict]
    device: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True