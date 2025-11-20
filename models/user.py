from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from db.database import Base
import uuid
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    email = Column(String)
    chronotype = Column(String)
    ai_status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)