from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import time

from db.database import engine, Base

# models を import しておく（create_all がテーブルを認識するため）
from models.user import User
from models.task import Task
from models.event_log import EventLog
from models.plant import Plant

from routers import auth, tasks, event_logs, ai, plants
from services.ml_score_service import load_model


app = FastAPI()

# 起動時間の記録（任意）
STARTED_AT = time.time()
app.state.model_loaded = False

# --- CORS設定（開発用：本番は allow_origins を絞るの推奨）---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ルーター ---
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(event_logs.router)
app.include_router(ai.router)
app.include_router(plants.router)  # ← 追加（元コードにあったのに include されてなかった）


@app.on_event("startup")
def _startup():
    """
    Render起動時に1回だけ実行される処理
    - DBテーブル作成
    - MLモデルロード
    """
    # DBテーブル作成（import時ではなく起動時に回す）
    Base.metadata.create_all(bind=engine)

    # MLモデルロード（重いなら try/except で落ちないようにするのもアリ）
    load_model()
    app.state.model_loaded = True


# --- コールドスタート対策：超軽量エンドポイント（DB/MLに触らない） ---
@app.get("/ping", include_in_schema=False)
def ping():
    return {
        "ok": True,
        "service": "watnow-backend",
        "ts": datetime.now(timezone.utc).isoformat(),
        "uptime_sec": round(time.time() - STARTED_AT, 2),
        "model_loaded": bool(getattr(app.state, "model_loaded", False)),
    }
