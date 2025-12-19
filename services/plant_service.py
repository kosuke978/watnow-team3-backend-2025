from sqlalchemy.orm import Session
from models.plant import Plant
from models.task import Task
from datetime import datetime, timedelta
import uuid


def get_week_start(dt: datetime = None) -> datetime:
    """
    指定された日時(デフォルトは現在UTC時刻)を含む週の月曜日00:00:00を返す
    """
    if dt is None:
        dt = datetime.utcnow()
    
    # 曜日を取得 (月曜=0, 日曜=6)
    weekday = dt.weekday()
    
    # 今週の月曜日を計算
    monday = dt - timedelta(days=weekday)
    
    # 時刻を00:00:00にリセット
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def update_plant_level(user_id: uuid.UUID, db: Session) -> dict:
    """
    ユーザーの植物レベルを週次タスク完了率に基づいて更新する
    
    Args:
        user_id: ユーザーID
        db: データベースセッション
    
    Returns:
        dict: {
            "current_level": int,      # 更新後のレベル (0-10)
            "leveled_up": bool,        # 前回より上がったかどうか
            "message": str             # フロント表示用メッセージ
        }
    """
    # 今週の開始日時を取得 (月曜日 00:00:00 UTC)
    week_start = get_week_start()
    
    # 今週作成されたタスクを取得
    total_tasks = db.query(Task).filter(
        Task.user_id == user_id,
        Task.created_at >= week_start
    ).count()
    
    # 今週作成されたタスクのうち完了したものを取得
    completed_tasks = db.query(Task).filter(
        Task.user_id == user_id,
        Task.created_at >= week_start,
        Task.status == "completed"
    ).count()
    
    # レベルを計算
    if total_tasks == 0:
        new_level = 0
    else:
        completion_rate = completed_tasks / total_tasks
        new_level = min(int(completion_rate * 10), 10)  # 0-10の範囲に制限
    
    # 植物レコードを取得または作成
    plant = db.query(Plant).filter(Plant.user_id == user_id).first()
    
    if plant is None:
        # 植物が存在しない場合は新規作成
        plant = Plant(
            user_id=user_id,
            level=new_level,
            last_updated=datetime.utcnow()
        )
        db.add(plant)
        previous_level = 0
    else:
        # 既存の植物のレベルを更新
        previous_level = plant.level
        plant.level = new_level
        plant.last_updated = datetime.utcnow()
    
    db.commit()
    db.refresh(plant)
    
    # レベルアップしたかどうかを判定
    leveled_up = new_level > previous_level
    
    # メッセージを生成
    if leveled_up:
        message = "植物が育ちました！"
    elif new_level < previous_level:
        message = "植物のレベルが下がりました"
    else:
        message = "植物のレベルは変わりませんでした"
    
    return {
        "current_level": new_level,
        "leveled_up": leveled_up,
        "message": message
    }
