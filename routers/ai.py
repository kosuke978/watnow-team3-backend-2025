# routers/ai.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from models.task import Task
from models.event_log import EventLog
from schemas.event_log import EventType
from auth.deps import get_current_user
from services.ai_service import calculate_scores, generate_feedback
from schemas.ai import AIInput, AIUser, AIScore, AISummary, AIPatterns
import datetime

router = APIRouter(prefix="/ai", tags=["AI"])

def _fmt_hhmm(dt: datetime.datetime) -> str:
    return dt.strftime("%H:%M")

def _parse_iso(dt_str: str) -> datetime.datetime | None:
    try:
        # "2025-11-15T07:43:00Z" みたいなZ付き対策
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(dt_str)
    except Exception:
        return None

def _calc_streak_days(tasks: list[Task], today: datetime.date) -> int:
    """
    completed_at から「今日までの連続完了日数」を計算
    ※ “その日に1個でも完了があれば達成” 扱い
    """
    done_dates = set()
    for t in tasks:
        if t.completed_at:
            done_dates.add(t.completed_at.date())

    streak = 0
    d = today
    while d in done_dates:
        streak += 1
        d = d - datetime.timedelta(days=1)
    return streak

@router.post("/feedback")
def ai_feedback(db: Session = Depends(get_db), user=Depends(get_current_user)):
    today = datetime.date.today()
    start = datetime.datetime.combine(today, datetime.time.min)
    end = datetime.datetime.combine(today, datetime.time.max)

    logs: list[EventLog] = (
        db.query(EventLog)
        .filter(
            EventLog.user_id == user.user_id,
            EventLog.timestamp >= start,
            EventLog.timestamp <= end,
        )
        .order_by(EventLog.timestamp.asc())
        .all()
    )

    # タスクは広めに取る（streak計算に過去が要る）
    tasks: list[Task] = (
        db.query(Task)
        .filter(Task.user_id == user.user_id)
        .all()
    )

    # -------------------------
    # wake_time をログから作る
    # -------------------------
    wake_time = "00:00"
    wake_log = next((l for l in logs if l.event_type == EventType.WAKE_TIME_LOGGED.value and l.data), None)
    if wake_log and isinstance(wake_log.data, dict) and wake_log.data.get("time"):
        dt = _parse_iso(wake_log.data["time"])
        if dt:
            wake_time = _fmt_hhmm(dt)

    # daily_check_in の有無
    daily_check_in = any(l.event_type == EventType.DAILY_CHECK_IN.value for l in logs)

    # streak_days（tasks.completed_at から算出）
    streak_days = _calc_streak_days(tasks, today)

    # first_action_time（今日のログの最初）
    first_action_time = _fmt_hhmm(logs[0].timestamp) if logs else "00:00"

    # -------------------------
    # patterns を logs から作る
    # -------------------------
    # most_active_hour: ログが最も多い時間帯
    hour_counts: dict[int, int] = {}
    for l in logs:
        h = l.timestamp.hour
        hour_counts[h] = hour_counts.get(h, 0) + 1
    most_active_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0

    # task_creation_hour: task_created が一番多い時間
    create_hour_counts: dict[int, int] = {}
    for l in logs:
        if l.event_type == EventType.TASK_CREATED.value:
            h = l.timestamp.hour
            create_hour_counts[h] = create_hour_counts.get(h, 0) + 1
    task_creation_hour = max(create_hour_counts, key=create_hour_counts.get) if create_hour_counts else 0

    # is_morning_person: wake_time が 4-9 なら一旦 True 扱い（暫定ルール）
    is_morning_person = False
    if wake_log and isinstance(wake_log.data, dict) and wake_log.data.get("time"):
        dt = _parse_iso(wake_log.data["time"])
        if dt and 4 <= dt.hour <= 9:
            is_morning_person = True

    summary = AISummary(
        completed_tasks=sum(1 for t in tasks if t.status == "completed"),
        overdue_tasks=sum(1 for t in tasks if t.status == "missed"),
        streak_days=streak_days,
        first_action_time=first_action_time,
        wake_time=wake_time,
    )

    patterns = AIPatterns(
        most_active_hour=most_active_hour,
        task_creation_hour=task_creation_hour,
        is_morning_person=is_morning_person,
    )

    # スコア計算（logsから算出するように ai_service 側を改善する）
    score_dict = calculate_scores(logs, tasks, user)
    # daily_check_in を ai_service が見るために input_data にも入れたいなら summary に含めてもOKやけど、
    # 今回は ai_service 内で logs を見て判断する前提にする
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

    result = generate_feedback(input_data.model_dump())
    return result