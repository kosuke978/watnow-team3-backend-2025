from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class PlantResponse(BaseModel):
    plant_id: UUID
    user_id: UUID
    level: int
    last_updated: datetime

    class Config:
        orm_mode = True


class PlantUpdateResult(BaseModel):
    """植物レベル更新結果"""
    current_level: int
    leveled_up: bool
    message: str
