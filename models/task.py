from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from db.database import Base
import uuid
from datetime import datetime

class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    title = Column(String, nullable=False)
    due_date = Column(DateTime)
    self_due_date = Column(DateTime)
    priority = Column(Integer)  # 1〜3
    category = Column(String)
    status = Column(String)  # pending / completed / missed
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)