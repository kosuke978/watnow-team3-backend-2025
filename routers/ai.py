from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db

from models.task import Task
from models.event_log import EventLog
from auth.deps import get_current_user

from services.ai_service import calculate_scores, generate_feedback
from services.ml_score_service import predict_total_score_debug  # ★変更（debug付き）

from schemas.ai import AIInput, AIUser, AIScore, AISummary, AIPatterns
import datetime

router = APIRouter(prefix="/ai", tags=["AI"])


# -------------------------
# utils
# -------------------------
def _fmt_hhmm(dt: datetime.datetime) -> str:
    return dt.strftime("%H:%M")


def _parse_iso(dt_str: str) -> datetime.datetime | None:
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _calc_streak_days(tasks: list[Task], today: datetime.date) -> int:
    """
    completed_at から「今日までの連続完了日数」を計算
    その日に1つでも完了があればOK
    """
    done_dates = set()
    for t in tasks:
        if t.completed_at:
            done_dates.add(t.completed_at.date())

    streak = 0
    d = today
    while d in done_dates:
        streak += 1
        d -= datetime.timedelta(days=1)

    return streak


# -------------------------
# endpoint
# -------------------------
@router.post("/feedback")
def ai_feedback(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    today = datetime.date.today()
    start = datetime.datetime.combine(today, datetime.time.min)
    end = datetime.datetime.combine(today, datetime.time.max)

    # 今日のログ
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

    # タスクは過去分も含めて取得（streak用）
    tasks: list[Task] = (
        db.query(Task)
        .filter(Task.user_id == user.user_id)
        .all()
    )

    # -------------------------
    # wake_time
    # -------------------------
    wake_time = "00:00"
    wake_log = next(
        (l for l in logs if l.event_type == "wake_time_logged" and isinstance(l.data, dict)),
        None,
    )
    if wake_log and wake_log.data.get("time"):
        dt = _parse_iso(wake_log.data["time"])
        if dt:
            wake_time = _fmt_hhmm(dt)

    # -------------------------
    # daily_check_in
    # -------------------------
    daily_check_in = any(l.event_type == "daily_check_in" for l in logs)

    # -------------------------
    # streak_days
    # -------------------------
    streak_days = _calc_streak_days(tasks, today)

    # -------------------------
    # first_action_time
    # -------------------------
    first_action_time = _fmt_hhmm(logs[0].timestamp) if logs else "00:00"

    # -------------------------
    # patterns
    # -------------------------
    # most_active_hour
    hour_counts: dict[int, int] = {}
    for l in logs:
        h = l.timestamp.hour
        hour_counts[h] = hour_counts.get(h, 0) + 1
    most_active_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0

    # task_creation_hour
    create_hour_counts: dict[int, int] = {}
    for l in logs:
        if l.event_type == "task_created":
            h = l.timestamp.hour
            create_hour_counts[h] = create_hour_counts.get(h, 0) + 1
    task_creation_hour = max(create_hour_counts, key=create_hour_counts.get) if create_hour_counts else 0

    # is_morning_person（暫定）
    is_morning_person = False
    if wake_log and wake_log.data.get("time"):
        dt = _parse_iso(wake_log.data["time"])
        if dt and 4 <= dt.hour <= 9:
            is_morning_person = True

    # -------------------------
    # summary
    # -------------------------
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

    # -------------------------
    # scores（ルールベース + ML total差し替え）
    # -------------------------
    score_dict = calculate_scores(logs, tasks, user)
    rule_total = int(score_dict.get("total", 0))

    ml_total, ml_features = predict_total_score_debug(logs, tasks, user)

    # ★ MLモデルがあれば total を差し替え
    if ml_total is not None:
        score_dict["total"] = int(round(ml_total))

    scores = AIScore(**score_dict)

    # -------------------------
    # AI input
    # -------------------------
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

    # ★開発用debug（後で消す）
    result["debug"] = {
        "rule_total": rule_total,
        "ml_total": int(round(ml_total)) if ml_total is not None else None,
        "ml_features": ml_features,  # 特徴量が一致してるか確認用
        "ml_used": ml_total is not None,
    }

    return result 