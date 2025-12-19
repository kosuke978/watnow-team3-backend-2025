# schemas/ai.py
from pydantic import BaseModel
from typing import Optional, Dict, Any

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

# Range対応の新しいスキーマ
class AIFeedbackSummary(BaseModel):
    completed: int
    pending: int
    missed: int
    completion_rate: float
    snooze_rate: float
    most_common_weekday: str
    most_active_time_bucket: str

class AIFeedbackDebug(BaseModel):
    rule_total: int
    ml_total: Optional[int]
    ml_features: Optional[Dict[str, Any]]
    ml_used: bool

class AIFeedbackResponse(BaseModel):
    message: str
    advice: str
    encourage: str
    summary: AIFeedbackSummary