# routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db

from models.task import Task
from models.event_log import EventLog
from schemas.task import TaskCreate, TaskUpdate, TaskResponse, TaskWithPlantResponse
from auth.deps import get_current_user
from services.plant_service import update_plant_level

from datetime import datetime, timezone
from uuid import UUID
from typing import List

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# -------------------------
# utility
# -------------------------
def to_naive_utc(dt: datetime | None):
    """
    aware / naive を問わず UTC naive に揃える
    """
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# -------------------------
# endpoints
# -------------------------
@router.get("/", response_model=List[TaskResponse])
def get_tasks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Task).filter(Task.user_id == user.user_id).all()


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
    task = db.query(Task).filter(
        Task.user_id == user.user_id,
        Task.task_id == task_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.put("/{task_id}", response_model=TaskWithPlantResponse)
def update_task(
    task_id: UUID,
    task_update: TaskUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    task = db.query(Task).filter(
        Task.user_id == user.user_id,
        Task.task_id == task_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    prev_status = task.status
    status_changed_to_completed = False

    # --- 更新処理 ---
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

        # completed に「初めて」変わった瞬間
        if task_update.status == "completed" and prev_status != "completed":
            task.completed_at = datetime.utcnow()
            status_changed_to_completed = True

        # completed 以外に戻したら completed_at を消す
        if task_update.status != "completed":
            task.completed_at = None

    task.updated_at = datetime.utcnow()

    # --- ログを自動生成（task_completed）---
    if status_changed_to_completed:
        due = to_naive_utc(task.due_date)
        comp = to_naive_utc(task.completed_at)

        log = EventLog(
            user_id=user.user_id,
            task_id=task.task_id,
            event_type="task_completed",
            device="backend",
            data={
                "completion_time": comp.isoformat() if comp else None,
                "was_overdue": bool(due and comp and comp > due),
                "source": "backend_auto",
            },
        )
        db.add(log)

    # 先に task / log を保存
    db.commit()
    db.refresh(task)

    # 植物レベル更新（中で commit されても OK）
    plant_update = update_plant_level(user.user_id, db)

    return {
        "task": task,
        "plant_update": plant_update
    }


@router.delete("/{task_id}")
def delete_task(task_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    task = db.query(Task).filter(
        Task.user_id == user.user_id,
        Task.task_id == task_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}