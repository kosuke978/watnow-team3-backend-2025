from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from db.database import get_db
from models.task import Task
from models.user import User
from schemas.task import TaskCreate, TaskUpdate, TaskResponse
from auth.deps import get_current_user

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"]
)


# ---------------------
#  Task 作成
# ---------------------
@router.post("/", response_model=TaskResponse)
def create_task(
    task: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    new_task = Task(
        user_id=user.user_id,
        title=task.title,
        due_date=task.due_date,
        self_due_date=task.self_due_date,
        priority=task.priority,
        category=task.category,
        status=task.status
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


# ---------------------
#  Task 全取得（認証ユーザーのみ）
# ---------------------
@router.get("/", response_model=List[TaskResponse])
def get_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    tasks = db.query(Task).filter(Task.user_id == user.user_id).all()
    return tasks


# ---------------------
#  Task 1件取得
# ---------------------
@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == user.user_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


# ---------------------
#  Task 更新
# ---------------------
@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    new_data: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == user.user_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 欲しいフィールドだけ更新
    update_data = new_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


# ---------------------
#  Task 削除
# ---------------------
@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    task = db.query(Task).filter(
        Task.task_id == task_id,
        Task.user_id == user.user_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}