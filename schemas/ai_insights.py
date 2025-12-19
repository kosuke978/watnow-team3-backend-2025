# schemas/ai_insights.py
from pydantic import BaseModel
from typing import Dict, Optional


class TaskStats(BaseModel):
    completed: int
    pending: int
    missed: int
    completion_rate: float  # 0.0 - 1.0


class SnoozeStats(BaseModel):
    snooze_count: int
    remind_count: int
    snooze_rate: float  # 0.0 - 1.0


class CompletionTimingPattern(BaseModel):
    # 例: {"0-5": 2, "6-11": 5, ...}
    buckets: Dict[str, int]


class WeekdayDistribution(BaseModel):
    # 例: {"Mon": 3, "Tue": 1, ...}
    counts: Dict[str, int]
    most_common: Optional[str] = None
    concentration: float  # max_count / total_completed（0.0-1.0）


class AIInsightsResponse(BaseModel):
    range: str  # "week" | "all"
    chronotype: str  # morning / night_owl / neutral
    task_stats: TaskStats
    snooze: SnoozeStats
    completion_timing: CompletionTimingPattern
    weekday: WeekdayDistribution