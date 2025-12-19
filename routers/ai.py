# routers/ai.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from db.database import get_db

from models.task import Task
from models.event_log import EventLog
from schemas.event_log import EventType
from auth.deps import get_current_user

from services.ai_service import calculate_scores, generate_feedback
from services.ml_score_service import predict_total_score_debug  # debug付き

from schemas.ai import AIInput, AIUser, AIScore, AISummary, AIPatterns
from schemas.ai_insights import (
    AIInsightsResponse,
    TaskStats,
    SnoozeStats,
    CompletionTimingPattern,
    WeekdayDistribution,
)

import datetime
from datetime import timedelta

router = APIRouter(prefix="/ai", tags=["AI"])

WEEKDAY_KEYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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


def _bucket_hour(h: int) -> str:
    if 0 <= h <= 5:
        return "0-5"
    if 6 <= h <= 11:
        return "6-11"
    if 12 <= h <= 17:
        return "12-17"
    return "18-23"


def _event_value(ev) -> str:
    """
    EventType(enum)が増減しても落ちないように、
    "文字列" で比較できる値に寄せる
    """
    if isinstance(ev, str):
        return ev
    try:
        return ev.value
    except Exception:
        return str(ev)


# -------------------------
# endpoint: feedback（既存）
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
    wake_log = next((l for l in logs if l.event_type == EventType.WAKE_TIME_LOGGED.value and l.data), None)
    if wake_log and isinstance(wake_log.data, dict) and wake_log.data.get("time"):
        dt = _parse_iso(wake_log.data["time"])
        if dt:
            wake_time = _fmt_hhmm(dt)

    # daily_check_in の有無
    daily_check_in = any(l.event_type == EventType.DAILY_CHECK_IN.value for l in logs)

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
        if l.event_type == EventType.TASK_CREATED.value:
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
        "ml_features": ml_features,
        "ml_used": ml_total is not None,
    }

    return result


# -------------------------
# endpoint: insights（新規）
# -------------------------
@router.get("/insights", response_model=AIInsightsResponse)
def ai_insights(
    range: str = Query("week", pattern="^(week|all)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    UI表示用インサイト
    - week: 直近7日（rolling）
    - all: 全期間
    """
    now = datetime.datetime.utcnow()
    start_dt: datetime.datetime | None = None
    if range == "week":
        start_dt = now - timedelta(days=7)

    # -------------------------
    # tasks（完了/未完了/ミス/完了率）
    # -------------------------
    task_q = db.query(Task).filter(Task.user_id == user.user_id)
    if start_dt is not None:
        # まずは created_at 기준で統一（仕様を固定）
        task_q = task_q.filter(Task.created_at >= start_dt)

    tasks = task_q.all()

    completed = sum(1 for t in tasks if t.status == "completed")
    pending = sum(1 for t in tasks if t.status == "pending")
    missed = sum(1 for t in tasks if t.status == "missed")

    total_tasks = completed + pending + missed
    completion_rate = (completed / total_tasks) if total_tasks > 0 else 0.0

    task_stats = TaskStats(
        completed=int(completed),
        pending=int(pending),
        missed=int(missed),
        completion_rate=float(completion_rate),
    )

    # -------------------------
    # logs（スヌーズ率/完了時間帯/曜日分布）
    # -------------------------
    log_q = db.query(EventLog).filter(EventLog.user_id == user.user_id)
    if start_dt is not None:
        log_q = log_q.filter(EventLog.timestamp >= start_dt)

    logs = log_q.order_by(EventLog.timestamp.asc()).all()

    # EventType が無い/未定義でも落ちないよう文字列比較に寄せる
    remind_sent_key = getattr(EventType, "REMIND_SENT", "remind_sent")
    remind_snoozed_key = getattr(EventType, "REMIND_SNOOZED", "remind_snoozed")
    task_completed_key = getattr(EventType, "TASK_COMPLETED", "task_completed")

    remind_sent_val = _event_value(remind_sent_key)
    remind_snoozed_val = _event_value(remind_snoozed_key)
    task_completed_val = _event_value(task_completed_key)

    snooze_count = sum(1 for l in logs if l.event_type == remind_snoozed_val)
    remind_count = sum(1 for l in logs if l.event_type == remind_sent_val)
    snooze_rate = (snooze_count / remind_count) if remind_count > 0 else 0.0

    snooze = SnoozeStats(
        snooze_count=int(snooze_count),
        remind_count=int(remind_count),
        snooze_rate=float(snooze_rate),
    )

    # -------------------------
    # 完了時間帯パターン（logs優先 → tasks.completed_atでfallback）
    # -------------------------
    timing_buckets = {"0-5": 0, "6-11": 0, "12-17": 0, "18-23": 0}

    completed_logs = [l for l in logs if l.event_type == task_completed_val and l.timestamp]
    if completed_logs:
        for l in completed_logs:
            timing_buckets[_bucket_hour(l.timestamp.hour)] += 1
    else:
        for t in tasks:
            if t.status == "completed" and t.completed_at:
                timing_buckets[_bucket_hour(t.completed_at.hour)] += 1

    completion_timing = CompletionTimingPattern(buckets=timing_buckets)

    # -------------------------
    # 曜日分布 + 習慣リズム（最多曜日/偏り）
    # -------------------------
    weekday_counts = {k: 0 for k in WEEKDAY_KEYS}
    completed_for_weekday = 0

    if completed_logs:
        for l in completed_logs:
            wd = l.timestamp.weekday()  # Mon=0..Sun=6
            weekday_counts[WEEKDAY_KEYS[wd]] += 1
        completed_for_weekday = len(completed_logs)
    else:
        for t in tasks:
            if t.status == "completed" and t.completed_at:
                wd = t.completed_at.weekday()
                weekday_counts[WEEKDAY_KEYS[wd]] += 1
                completed_for_weekday += 1

    most_common = None
    concentration = 0.0
    if completed_for_weekday > 0:
        most_common = max(weekday_counts, key=weekday_counts.get)
        concentration = weekday_counts[most_common] / completed_for_weekday

    weekday = WeekdayDistribution(
        counts=weekday_counts,
        most_common=most_common,
        concentration=float(concentration),
    )

    # -------------------------
    # chronotype（users.chronotype）
    # -------------------------
    chronotype = user.chronotype or "neutral"

    return AIInsightsResponse(
        range=range,
        chronotype=chronotype,
        task_stats=task_stats,
        snooze=snooze,
        completion_timing=completion_timing,
        weekday=weekday,
    )