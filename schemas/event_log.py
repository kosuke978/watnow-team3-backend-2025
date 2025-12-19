# schemas/event_log.py
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime
from uuid import UUID
from enum import Enum

class EventType(str, Enum):
    """イベントログの種別を定義するEnum"""
    DAILY_CHECK_IN = "daily_check_in"
    WAKE_TIME_LOGGED = "wake_time_logged"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_CREATED = "task_created"
    SCREEN_TRANSITION = "screen_transition"
    BUTTON_CLICKED = "button_clicked"

class EventLogCreate(BaseModel):
    task_id: Optional[UUID] = None
    event_type: EventType
    data: Optional[Dict] = None
    device: Optional[str] = None

class EventLogResponse(BaseModel):
    log_id: UUID
    user_id: UUID
    task_id: Optional[UUID]
    event_type: EventType
    data: Optional[Dict]
    device: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True