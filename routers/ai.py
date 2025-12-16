# routers/ai.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from models.task import Task
from models.event_log import EventLog
from auth.deps import get_current_user
from services.ai_service import calculate_scores, generate_feedback
from schemas.ai import AIInput, AIUser, AIScore, AISummary, AIPatterns
import datetime

router = APIRouter(prefix="/ai", tags=["AI"])

@router.post("/feedback")
def ai_feedback(db: Session = Depends(get_db), user=Depends(get_current_user)):

    today = datetime.date.today()
    start = datetime.datetime.combine(today, datetime.time.min)
    end = datetime.datetime.combine(today, datetime.time.max)

    logs = (
        db.query(EventLog)
        .filter(
            EventLog.user_id == user.user_id,
            EventLog.timestamp >= start,
            EventLog.timestamp <= end,
        )
        .order_by(EventLog.timestamp.asc())
        .all()
    )

    tasks = db.query(Task).filter(Task.user_id == user.user_id).all()

    summary = AISummary(
        completed_tasks=sum(1 for t in tasks if t.status == "completed"),
        overdue_tasks=sum(1 for t in tasks if t.status == "missed"),
        streak_days=0,  # TODO: streak実装したら差し替え
        first_action_time=logs[0].timestamp.strftime("%H:%M") if logs else "00:00",
        wake_time="09:00",  # TODO: wake_time_logged から取る
    )

    patterns = AIPatterns(
        most_active_hour=15,
        task_creation_hour=14,
        is_morning_person=False,
    )

    score_dict = calculate_scores(logs, tasks, user)
    scores = AIScore(**score_dict)

    input_data = AIInput(
        user_id=str(user.user_id),
        user=AIUser(
            name=user.name or "",
            chronotype=user.chronotype or "neutral",
            ai_status=user.ai_status or "default",
        ),
        scores=scores,
        summary=summary,
        patterns=patterns,
    )

    result = generate_feedback(input_data.dict())
    return result