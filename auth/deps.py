import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from db.database import get_db
from models.user import User

security = HTTPBearer()

# Supabase の JWT 秘密鍵（.env から読み込む）
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGORITHM = "HS256"  # Supabase Auth は HS256 署名方式

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Supabase Auth が発行した JWT を検証し、
    user_id を取り出して DB の users テーブルと紐付ける関数。

    すべての認証付き API で Depends(get_current_user) として利用する。
    """
    token = credentials.credentials

    # JWT 検証
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")  # Supabase Auth の user.id が sub に入る
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT token.",
        )

    # DB にユーザーが存在するか確認
    user = db.query(User).filter(User.user_id == user_id).first()

    # 初回ログイン時は自動作成する
    if user is None:
        user = User(user_id=user_id)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user