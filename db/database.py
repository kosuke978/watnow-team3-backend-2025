from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    echo=True,  # 開発中は SQL ログが見れる
)

# DB セッション生成
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base（すべてのモデルが継承）
Base = declarative_base()

# 🔥 get_db 関数（FastAPI で絶対必要）
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()