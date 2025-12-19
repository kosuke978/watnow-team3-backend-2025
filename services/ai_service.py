from openai import OpenAI
import os
from datetime import datetime
from typing import List, Tuple
from models.event_log import EventLog
from models.task import Task
from models.user import User
from schemas.event_log import EventType
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

IDLE_GAP_MINUTES = 15  # 無操作区間でセッションを分割


# -------------------------
# helpers
# -------------------------
def _parse_iso(dt_str: str) -> datetime | None:
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _extract_daily_check_in(logs: List[EventLog]) -> int:
    return 1 if any(l.event_type == EventType.DAILY_CHECK_IN.value for l in logs) else 0


def _pair_task_sessions(logs: List[EventLog]) -> List[Tuple[datetime, datetime]]:
    """
    task_started -> task_completed を task_id でペアにしてセッションを作る
    """
    started: dict[str, datetime] = {}
    sessions: List[Tuple[datetime, datetime]] = []

    for l in logs:
        if not l.task_id:
            continue
        tid = str(l.task_id)

        if l.event_type == EventType.TASK_STARTED.value:
            started[tid] = l.timestamp

        if l.event_type == EventType.TASK_COMPLETED.value:
            if tid in started:
                s = started.pop(tid)
                e = l.timestamp
                if e > s:
                    sessions.append((s, e))

    return sessions


def _activity_sessions_from_timestamps(logs: List[EventLog]) -> List[Tuple[datetime, datetime]]:
    """
    logs の時系列から、無操作(IDLE_GAP_MINUTES以上)で区切ってセッションを作る（補助用）
    """
    if not logs:
        return []

    ts = [l.timestamp for l in logs]
    ts.sort()

    sessions: List[Tuple[datetime, datetime]] = []
    cur_start = ts[0]
    cur_end = ts[0]

    for t in ts[1:]:
        gap = (t - cur_end).total_seconds() / 60
        if gap >= IDLE_GAP_MINUTES:
            sessions.append((cur_start, cur_end))
            cur_start = t
            cur_end = t
        else:
            cur_end = t

    sessions.append((cur_start, cur_end))
    return sessions


def _calc_session_metrics(logs: List[EventLog]) -> tuple[int, float]:
    """
    session_count, avg_session_minutes を返す
    優先: task_started/task_completed のペア
    補助: 活動セッション(無操作区間で分割)
    """
    paired = _pair_task_sessions(logs)

    durations = []
    for s, e in paired:
        durations.append((e - s).total_seconds() / 60)

    # ペアが少ない場合は、活動セッションでも補完
    if len(durations) < 1:
        act = _activity_sessions_from_timestamps(logs)
        for s, e in act:
            dur = (e - s).total_seconds() / 60
            if dur >= 1:
                durations.append(dur)

    if not durations:
        return 0, 0.0

    session_count = len(durations)
    avg_minutes = sum(durations) / len(durations)
    return session_count, avg_minutes


def _score_band(total: int) -> tuple[str, str]:
    """
    total_score(0-100想定) を「言い方」に変換する
    """
    if total >= 80:
        return ("great", "かなりええ流れの一日")
    if total >= 60:
        return ("good", "ええ感じに進んだ一日")
    if total >= 40:
        return ("ok", "まずまずの一日")
    return ("low", "今日は控えめな一日")


# -------------------------
# scoring (rule-based)
# -------------------------
def calculate_scores(logs: List[EventLog], tasks: List[Task], user: User):
    completed = sum(1 for t in tasks if t.status == "completed")
    overdue = sum(1 for t in tasks if t.status == "missed")

    daily_check_in = _extract_daily_check_in(logs)

    completion_rate = 0.0
    if (completed + overdue) > 0:
        completion_rate = completed / (completed + overdue)

    streak = 0  # ここは今0のままでもOK（summary側はroutersで出してる）

    CONSISTENCY = (
        40 * min(completed / 3, 1)
        + 30 * daily_check_in
        + 20 * min(streak / 7, 1)
        + 10 * completion_rate
    )

    session_count, avg_session_min = _calc_session_metrics(logs)

    # "画面移動/クリック多すぎ" ペナルティも入れたいならここで軽く
    screen_moves = sum(1 for l in logs if l.event_type == EventType.SCREEN_TRANSITION.value)
    button_clicks = sum(1 for l in logs if l.event_type == EventType.BUTTON_CLICKED.value)
    noise = screen_moves + button_clicks

    base_focus = 60 * min(session_count / 3, 1) + 40 * min(avg_session_min / 30, 1)
    penalty = min(noise / 50, 1) * 15
    FOCUS = max(base_focus - penalty, 0)

    # ---- Energy ----
    wake_time_log = next((l for l in logs if l.event_type == EventType.WAKE_TIME_LOGGED.value and l.data), None)
    first_action = logs[0].timestamp if logs else None

    wake_score = 0
    action_score = 0

    wake_dt = None
    if wake_time_log and isinstance(wake_time_log.data, dict) and wake_time_log.data.get("time"):
        wake_dt = _parse_iso(wake_time_log.data["time"])

    if wake_dt:
        hour = wake_dt.hour
        if 4 <= hour <= 9:
            wake_score = 100
        elif 9 < hour <= 12:
            wake_score = 50
        else:
            wake_score = 20

    if wake_dt and first_action:
        delta_h = (first_action - wake_dt).total_seconds() / 3600
        if delta_h <= 1:
            action_score = 100
        elif delta_h <= 3:
            action_score = 50
        else:
            action_score = 20

    ENERGY = 60 * (wake_score / 100) + 40 * (action_score / 100)

    TOTAL = 0.4 * FOCUS + 0.4 * CONSISTENCY + 0.2 * ENERGY

    return {
        "focus": int(FOCUS),
        "consistency": int(CONSISTENCY),
        "energy": int(ENERGY),
        "total": int(TOTAL),
    }


# -------------------------
# feedback generation (must include total feeling)
# -------------------------
def generate_feedback(input_data: dict):
    try:
        total = int(input_data.get("scores", {}).get("total", 0))
    except Exception:
        total = 0

    _, band_text = _score_band(total)

    prompt = f"""
あなたはユーザーの行動分析コーチです。
与えられた JSON の行動データとスコアを用いて、ユーザーに1日のフィードバックを返してください。

【今回の重要情報（必ず反映）】
- 今日の総合スコア（total）: {total}
- スコアの言い換え: 「{band_text}」
→ message には必ずこの言い換え（または同等表現）を入れてください。
→ 数値 {total} は「出しても出さなくてもOK」。ただし“雰囲気だけ”は禁止。

【出力形式】（JSON以外は禁止）
{{
  "message": "...",
  "advice": "...",
  "encourage": "..."
}}

【厳守ルール】
- 否定しない
- データに基づく根拠を書く（例：完了数、初動、アクティブ時間など）
- chronotype に合わせた文章にする
- 改善は1つだけ（adviceに1つ）
- 150〜220文字程度（3項目合計）
- 優しい語尾
- 精神論禁止
- 命令口調禁止

以下の JSON を解析してフィードバックを生成してください：
{json.dumps(input_data, ensure_ascii=False)}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful AI coach. Output MUST be a JSON object."},
                {"role": "user", "content": prompt},
            ],
        )
    except TypeError:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful AI coach. Output MUST be a JSON object."},
                {"role": "user", "content": prompt},
            ],
        )

    text = resp.choices[0].message.content or ""

    try:
        return json.loads(text)
    except Exception:
        return {
            "message": text,
            "advice": "",
            "encourage": "今日もお疲れさま。よう頑張ったで。",
        }