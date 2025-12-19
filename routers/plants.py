from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from auth.deps import get_current_user
from models.user import User
from models.plant import Plant
from schemas.plant import PlantResponse
from datetime import datetime

router = APIRouter(
    prefix="/plants",
    tags=["Plants"],
)

@router.get("/me", response_model=PlantResponse)
def get_my_plant(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    現在ログイン中のユーザーの植物データを取得
    存在しない場合は level=0 で新規作成
    """
    # ユーザーの植物を取得
    plant = db.query(Plant).filter(Plant.user_id == user.user_id).first()
    
    # 存在しない場合は新規作成
    if plant is None:
        plant = Plant(
            user_id=user.user_id,
            level=0,
            last_updated=datetime.utcnow()
        )
        db.add(plant)
        db.commit()
        db.refresh(plant)
    
    return plant
