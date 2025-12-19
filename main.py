from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.database import engine, Base

from models.user import User
from models.task import Task
from models.event_log import EventLog
from models.plant import Plant

from routers import auth, tasks, event_logs, ai, plants

from services.ml_score_service import load_model  # ★追加

app = FastAPI()

# CORS設定
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# モデルを読み込んだあとにテーブル作成
Base.metadata.create_all(bind=engine)

# ルーター
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(event_logs.router)
app.include_router(ai.router)
app.include_router(plants.router)

# 起動時に1回だけMLモデルをロード
@app.on_event("startup")
def _startup():
    load_model()
