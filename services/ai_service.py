# services/ai_service.py
from openai import OpenAI
import os
from datetime import datetime
from typing import List
from models.event_log import EventLog
from models.task import Task
from models.user import User
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def calculate_scores(logs: List[EventLog], tasks: List[Task], user: User):
    # ---- Consistency ----
    completed = sum(1 for t in tasks if t.status == "completed")
    overdue = sum(1 for t in tasks if t.status == "missed")
    streak = 0  # 今はUserにカラム無いので0固定

    if completed + overdue == 0:
        completion_rate = 0
    else:
        completion_rate = completed / (completed + overdue)

    CONSISTENCY = (
        40 * min(completed / 3, 1)
        + 30 * 1  # とりあえず daily_check_in=1 とみなす
        + 20 * min(streak / 7, 1)
        + 10 * completion_rate
    )

    # ---- Focus（今はダミー）----
    session_count = 0
    avg_session_min = 10
    FOCUS = 60 * min(session_count / 3, 1) + 40 * min(avg_session_min / 30, 1)

    # ---- Energy ----
    wake_time_log = next((l for l in logs if l.event_type == "wake_time_logged" and l.data), None)
    first_action = logs[0].timestamp if logs else None

    if wake_time_log and wake_time_log.data.get("time"):
        t = datetime.fromisoformat(wake_time_log.data["time"])
        hour = t.hour
        if 4 <= hour <= 9:
            wake_score = 100
        elif 9 < hour <= 12:
            wake_score = 50
        else:
            wake_score = 20
    else:
        wake_score = 0

    if wake_time_log and first_action and wake_time_log.data.get("time"):
        wake_dt = datetime.fromisoformat(wake_time_log.data["time"])
        delta = (first_action - wake_dt).total_seconds() / 3600
        if delta <= 1:
            action_score = 100
        elif delta <= 3:
            action_score = 50
        else:
            action_score = 20
    else:
        action_score = 0

    ENERGY = 60 * (wake_score / 100) + 40 * (action_score / 100)

    TOTAL = 0.4 * FOCUS + 0.4 * CONSISTENCY + 0.2 * ENERGY

    return {
        "focus": int(FOCUS),
        "consistency": int(CONSISTENCY),
        "energy": int(ENERGY),
        "total": int(TOTAL)
    }

def generate_feedback(input_data: dict):
    prompt = f"""
あなたはユーザーの行動分析コーチです。
与えられた JSON の行動データとスコアを用いて、
ユーザーに1日のフィードバックを返してください。

【出力形式】
{{
 "message": "...",
 "advice": "...",
 "encourage": "..."
}}

【厳守ルール】
- 否定しない
- データに基づく根拠を書く
- chronotype に合わせた文章にする
- 改善は1つだけ
- 150〜220文字程度
- 優しい語尾
- 精神論禁止
- 命令口調禁止

以下の JSON を解析してフィードバックを生成してください：

{json.dumps(input_data, ensure_ascii=False)}
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful AI coach."},
            {"role": "user", "content": prompt},
        ]
    )

    text = resp.choices[0].message.content

    try:
        data = json.loads(text)
        return data
    except Exception:
        return {
            "message": text,
            "advice": "",
            "encourage": "今日もお疲れさま。よう頑張ったで。"
        }