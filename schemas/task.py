# schemas/task.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID
from schemas.plant import PlantUpdateResult

class TaskBase(BaseModel):
    title: str
    due_date: Optional[datetime] = None
    self_due_date: Optional[datetime] = None
    priority: Optional[int] = 1
    category: Optional[str] = None
    status: Optional[str] = "pending"

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[datetime] = None
    self_due_date: Optional[datetime] = None
    priority: Optional[int] = None
    category: Optional[str] = None
    status: Optional[str] = None
    completed_at: Optional[datetime] = None

class TaskResponse(TaskBase):
    task_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True  # pydantic v2


class TaskWithPlantResponse(BaseModel):
    task: TaskResponse
    plant_update: PlantUpdateResult