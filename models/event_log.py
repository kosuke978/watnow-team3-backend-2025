from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from db.database import Base
import uuid
from datetime import datetime

class EventLog(Base):
    __tablename__ = "event_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    #ここが超重要
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)

    # task_id も UUID に合わせておく
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.task_id"), nullable=True)

    event_type = Column(String, nullable=False)
    data = Column(JSON)
    device = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)