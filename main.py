from fastapi import FastAPI
from db.database import engine, Base

from models.user import User
from models.task import Task
from routers import auth
from routers import tasks
from routers import event_logs

app = FastAPI()

# モデルを読み込んだあとにテーブル作成
Base.metadata.create_all(bind=engine)

# auth ルーター（prefix=/auth）
app.include_router(auth.router)

# tasks ルーター（prefix=/tasks）
app.include_router(tasks.router)

# event_logs ルーター（prefix=/event_logs）
app.include_router(event_logs.router)