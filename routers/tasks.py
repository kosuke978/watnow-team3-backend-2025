# routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from models.task import Task
from schemas.task import TaskCreate, TaskUpdate, TaskResponse, TaskWithPlantResponse
from auth.deps import get_current_user
from services.plant_service import update_plant_level
from datetime import datetime
from uuid import UUID
from typing import List

router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.get("/", response_model=List[TaskResponse])
def get_tasks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    tasks = db.query(Task).filter(Task.user_id == user.user_id).all()
    return tasks

@router.post("/", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    new_task = Task(
        user_id=user.user_id,
        title=task.title,
        due_date=task.due_date,
        self_due_date=task.self_due_date,
        priority=task.priority,
        category=task.category,
        status=task.status,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.user_id == user.user_id, Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.put("/{task_id}", response_model=TaskWithPlantResponse)
def update_task(task_id: UUID, task_update: TaskUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.user_id == user.user_id, Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task_update.title is not None:
        task.title = task_update.title
    if task_update.due_date is not None:
        task.due_date = task_update.due_date
    if task_update.self_due_date is not None:
        task.self_due_date = task_update.self_due_date
    if task_update.priority is not None:
        task.priority = task_update.priority
    if task_update.category is not None:
        task.category = task_update.category
    if task_update.status is not None:
        task.status = task_update.status

        if task_update.status == "completed" and task.completed_at is None:
            task.completed_at = datetime.utcnow()
        if task_update.status != "completed":
            task.completed_at = None

    task.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(task)
    
    # 植物レベルを更新
    plant_update = update_plant_level(user.user_id, db)
    
    # タスク情報と植物更新情報を返す
    return {
        "task": task,
        "plant_update": plant_update
    }

@router.delete("/{task_id}")
def delete_task(task_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    task = db.query(Task).filter(Task.user_id == user.user_id, Task.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}