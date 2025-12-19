from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

import joblib

from models.event_log import EventLog
from models.task import Task
from models.user import User


_MODEL = None  # 起動時に1回だけロードして保持

FEATURES = [
    "completed_tasks",
    "overdue_tasks",
    "streak_days",
    "completion_rate",
    "daily_check_in",
    "session_count",
    "avg_session_minutes",
    "wake_hour",
    "first_action_delay_hours",
]


# -------------------------
# datetime helpers
# -------------------------
def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """aware/naive混在をUTC naiveに揃える"""
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_iso(dt_str: str) -> Optional[datetime]:
    """Z付きISOもパースできるようにする"""
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


# -------------------------
# model load
# -------------------------
def load_model() -> None:
    """
    FastAPI起動時に1回だけ呼ぶ想定。
    毎リクエストロードしない。
    """
    global _MODEL

    base_dir = os.path.dirname(os.path.dirname(__file__))  # project root
    default_path = os.path.join(base_dir, "ml_models", "daily_score_model.pkl")
    model_path = os.getenv("DAILY_SCORE_MODEL_PATH", default_path)

    if not os.path.exists(model_path):
        _MODEL = None
        print(f"[ml_score_service] model not found: {model_path} (fallback to rule-based)")
        return

    _MODEL = joblib.load(model_path)
    print(f"[ml_score_service] model loaded: {model_path}")


# -------------------------
# session features (task logs)
# -------------------------
def _pair_task_sessions(logs: List[EventLog]) -> List[Tuple[datetime, datetime]]:
    """
    task_started -> task_completed を task_id でペアにしてセッション化
    """
    started: dict[str, datetime] = {}
    sessions: List[Tuple[datetime, datetime]] = []

    for l in logs:
        if not l.task_id:
            continue
        tid = str(l.task_id)

        ts = _to_naive_utc(l.timestamp) or l.timestamp

        if l.event_type == "task_started":
            started[tid] = ts

        if l.event_type == "task_completed" and tid in started:
            s = started.pop(tid)
            e = ts
            if e > s:
                sessions.append((s, e))

    return sessions


def _calc_session_metrics_from_tasks(logs: List[EventLog]) -> tuple[int, float]:
    paired = _pair_task_sessions(logs)
    if not paired:
        return 0, 0.0

    mins = [(e - s).total_seconds() / 60.0 for s, e in paired]
    return len(mins), float(sum(mins) / len(mins))


# -------------------------
# features
# -------------------------
def _extract_features(
    logs: List[EventLog],
    tasks: List[Task],
    user: User,
) -> Dict[str, Any]:
    """
    学習時の特徴量に合わせて作る（順番は FEATURES で統一）
    """
    completed_tasks = sum(1 for t in tasks if t.status == "completed")
    overdue_tasks = sum(1 for t in tasks if t.status == "missed")

    denom = completed_tasks + overdue_tasks
    completion_rate = (completed_tasks / denom) if denom > 0 else 0.0

    # streak_days は今DBで安定して出せないなら0でOK（後で routers側の算出に合わせて差し替え）
    streak_days = 0

    daily_check_in = 1 if any(l.event_type == "daily_check_in" for l in logs) else 0

    # session metrics（task_started/task_completed）
    session_count, avg_session_minutes = _calc_session_metrics_from_tasks(logs)

    # 何も取れない時のfallback（モデルが極端に外れんように）
    if session_count == 0 and avg_session_minutes == 0.0:
        avg_session_minutes = 10.0

    # wake_hour / first_action_delay_hours
    wake_hour = 9
    first_action_delay_hours = 5.0

    wake_log = next((l for l in logs if l.event_type == "wake_time_logged" and isinstance(l.data, dict)), None)
    if wake_log and wake_log.data.get("time"):
        wake_dt = _parse_iso(str(wake_log.data["time"]))
        wake_dt = _to_naive_utc(wake_dt)

        if wake_dt:
            wake_hour = int(wake_dt.hour)

            # 起床ログ以外で最初のログ
            first_action_log = next((x for x in logs if x.event_type != "wake_time_logged"), None)
            if first_action_log:
                fa = _to_naive_utc(first_action_log.timestamp)
                if fa:
                    diff = (fa - wake_dt).total_seconds() / 3600.0
                    first_action_delay_hours = float(max(diff, 0.0))

    return {
        "completed_tasks": int(completed_tasks),
        "overdue_tasks": int(overdue_tasks),
        "streak_days": int(streak_days),
        "completion_rate": float(completion_rate),
        "daily_check_in": int(daily_check_in),
        "session_count": int(session_count),
        "avg_session_minutes": float(avg_session_minutes),
        "wake_hour": int(wake_hour),
        "first_action_delay_hours": float(first_action_delay_hours),
    }


# -------------------------
# predict
# -------------------------
def predict_total_score(logs: List[EventLog], tasks: List[Task], user: User) -> Optional[float]:
    if _MODEL is None:
        return None

    feats = _extract_features(logs, tasks, user)
    X = [[feats[f] for f in FEATURES]]

    pred = _MODEL.predict(X)[0]
    return float(pred)


def predict_total_score_debug(
    logs: List[EventLog],
    tasks: List[Task],
    user: User,
) -> tuple[Optional[float], Dict[str, Any]]:
    """
    (pred, features) を返す。モデル無い時は (None, features)。
    """
    feats = _extract_features(logs, tasks, user)

    if _MODEL is None:
        return None, feats

    X = [[feats[f] for f in FEATURES]]
    pred = _MODEL.predict(X)[0]
    return float(pred), feats