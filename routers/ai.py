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
# endpoint: feedback（range対応版）
# -------------------------
@router.post("/feedback")
def ai_feedback(
    range: str = Query("week", pattern="^(week|all)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from schemas.ai import AIFeedbackResponse, AIFeedbackSummary
    
    now = datetime.datetime.now()
    today = datetime.date.today()
    
    # range に応じた期間設定
    if range == "week":
        start_dt = now - timedelta(days=7)
    else:
        start_dt = datetime.datetime.min
    
    end_dt = now

    # 期間内のログを取得
    logs: list[EventLog] = (
        db.query(EventLog)
        .filter(
            EventLog.user_id == user.user_id,
            EventLog.timestamp >= start_dt,
            EventLog.timestamp <= end_dt,
        )
        .order_by(EventLog.timestamp.asc())
        .all()
    )

    # 期間内のタスクを取得
    tasks: list[Task] = (
        db.query(Task)
        .filter(
            Task.user_id == user.user_id,
            Task.created_at >= start_dt,
            Task.created_at <= end_dt,
        )
        .all()
    )
    
    # -------------------------
    # 集計処理（/ai/insightsと同等）
    # -------------------------
    completed = sum(1 for t in tasks if t.status == "completed")
    pending = sum(1 for t in tasks if t.status == "pending")
    missed = sum(1 for t in tasks if t.status == "missed")
    
    completion_rate = 0.0
    if (completed + missed) > 0:
        completion_rate = completed / (completed + missed)
    
    # スヌーズ率（イベントタイプが存在しないため暫定で0）
    snooze_rate = 0.0
    
    # 曜日別分布
    weekday_counts = {day: 0 for day in WEEKDAY_KEYS}
    for t in tasks:
        if t.completed_at:
            wd_idx = t.completed_at.weekday()
            weekday_counts[WEEKDAY_KEYS[wd_idx]] += 1
    most_common_weekday = max(weekday_counts, key=weekday_counts.get) if weekday_counts else "Mon"
    
    # 時間帯別分布
    time_buckets = {"0-5": 0, "6-11": 0, "12-17": 0, "18-23": 0}
    for t in tasks:
        if t.completed_at:
            h = t.completed_at.hour
            if 0 <= h <= 5:
                time_buckets["0-5"] += 1
            elif 6 <= h <= 11:
                time_buckets["6-11"] += 1
            elif 12 <= h <= 17:
                time_buckets["12-17"] += 1
            else:
                time_buckets["18-23"] += 1
    most_active_time_bucket = max(time_buckets, key=time_buckets.get) if time_buckets else "0-5"
    
    summary_data = AIFeedbackSummary(
        completed=completed,
        pending=pending,
        missed=missed,
        completion_rate=completion_rate,
        snooze_rate=snooze_rate,
        most_common_weekday=most_common_weekday,
        most_active_time_bucket=most_active_time_bucket,
    )

    # -------------------------
    # scores（ルールベース + ML total差し替え）
    # -------------------------
    score_dict = calculate_scores(logs, tasks, user)
    rule_total = int(score_dict.get("total", 0))

    ml_total, ml_features = predict_total_score_debug(logs, tasks, user)

    final_total = rule_total
    if ml_total is not None:
        final_total = int(round(ml_total))

    # -------------------------
    # AI生成（新形式）
    # -------------------------
    chronotype = user.chronotype or "neutral"
    feedback_dict = generate_feedback(
        chronotype=chronotype,
        total_score=final_total,
        summary=summary_data.model_dump(),
        range_type=range
    )
    
    return AIFeedbackResponse(
        message=feedback_dict.get("message", ""),
        advice=feedback_dict.get("advice", ""),
        encourage=feedback_dict.get("encourage", ""),
        summary=summary_data,
    )


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