# schemas/event_log.py

from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

class EventLogCreate(BaseModel):
    task_id: Optional[str] = None
    event_type: str
    data: Optional[Dict] = None        # ← metadata → data
    device: Optional[str] = None

class EventLogResponse(BaseModel):
    log_id: str
    user_id: str
    task_id: Optional[str]
    event_type: str
    data: Optional[Dict]               # ← metadata → data
    device: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True