import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from db.database import get_db
from models.user import User

security = HTTPBearer()

# .env から取得。必ず Supabase の "JWT Secret" (API設定にあるもの) を設定してください
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGORITHM = "HS256"  # Supabase Auth は HS256 固定

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        # SupabaseのJWTには 'aud': 'authenticated' が含まれており、
        # デフォルトの検証ではエラーになることが多いため、verify_aud を False に設定します。
        payload = jwt.decode(
            token, 
            JWT_SECRET, 
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False}
        )
        
        user_id = payload.get("sub")
        if not user_id:
            print("❌ [DEBUG] JWTに 'sub' (User ID) が含まれていません")
            raise JWTError("Missing subject claim")
            
    except JWTError as e:
        # ターミナルにエラー内容を詳しく表示して原因を突き止めやすくします
        print(f"❌ [DEBUG] JWT検証エラー: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired JWT token: {str(e)}",
        )

    # ユーザーをデータベースから取得
    user = db.query(User).filter(User.user_id == user_id).first()

    # 初回ログイン時は自動作成
    if user is None:
        print(f"🆕 [DEBUG] 新規ユーザー登録: {user_id}")
        try:
            user = User(user_id=user_id)
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            print(f"❌ [DEBUG] ユーザー作成失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create user in database."
            )

    return user