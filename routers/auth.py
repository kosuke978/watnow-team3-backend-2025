from fastapi import APIRouter, Depends
from auth.deps import get_current_user
from models.user import User

# ここで /auth プレフィックスを付ける
router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    """
    現在ログイン中のユーザー情報を返すAPI
    （JWTが正しく検証されないと動かない）
    """
    return {
        "user_id": str(user.user_id),
        "chronotype": user.chronotype,
        "ai_status": user.ai_status,
        "created_at": user.created_at,
    }