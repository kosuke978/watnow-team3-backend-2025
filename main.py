# main.py
from fastapi import FastAPI
from db.database import engine, Base

from models.user import User
from models.task import Task
from models.event_log import EventLog
from models.plant import Plant

from routers import auth, tasks, event_logs, ai, plants

app = FastAPI()

Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(event_logs.router)
app.include_router(ai.router)
app.include_router(plants.router)