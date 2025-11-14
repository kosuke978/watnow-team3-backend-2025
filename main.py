from fastapi import FastAPI
from db.database import engine, Base

from models.user import User
from models.task import Task
from routers import auth

app = FastAPI()

# モデルを読み込んだあとにテーブル作成
Base.metadata.create_all(bind=engine)

# ここでは prefix を付けない！！
app.include_router(auth.router)