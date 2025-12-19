from fastapi import FastAPI
from db.database import engine, Base

from models.user import User
from models.task import Task
from models.event_log import EventLog
from models.plant import Plant

from routers import auth, tasks, event_logs, ai, plants

from services.ml_score_service import load_model  # ★追加

app = FastAPI()

# モデルを読み込んだあとにテーブル作成
Base.metadata.create_all(bind=engine)

# ルーター
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(event_logs.router)
app.include_router(ai.router)

# 起動時に1回だけMLモデルをロード
@app.on_event("startup")
def _startup():
    load_model()
app.include_router(plants.router)
