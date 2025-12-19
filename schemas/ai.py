# schemas/ai.py
from pydantic import BaseModel

class AIScore(BaseModel):
    focus: int
    consistency: int
    energy: int
    total: int

class AISummary(BaseModel):
    completed_tasks: int
    overdue_tasks: int
    streak_days: int
    first_action_time: str
    wake_time: str

class AIPatterns(BaseModel):
    most_active_hour: int
    task_creation_hour: int
    is_morning_person: bool

class AIUser(BaseModel):
    name: str
    chronotype: str
    ai_status: str

class AIInput(BaseModel):
    user_id: str
    user: AIUser
    scores: AIScore
    summary: AISummary
    patterns: AIPatterns