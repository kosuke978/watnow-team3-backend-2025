from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # ★追加
from db.database import engine, Base

# ... (既存のインポート) ...
from routers import auth, tasks, event_logs, ai, plants
from services.ml_score_service import load_model

app = FastAPI()

# --- CORS設定 ここから ★追加 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # すべてのオリジンからのアクセスを許可（開発用）
    allow_credentials=True,
    allow_methods=["*"],    # 全てのHTTPメソッド（GET, POST, etc.）を許可
    allow_headers=["*"],    # 全てのヘッダー（Authorization, Content-Type, etc.）を許可
)
# --- CORS設定 ここまで ---

# モデルを読み込んだあとにテーブル作成
Base.metadata.create_all(bind=engine)

# ルーター
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(event_logs.router)
app.include_router(ai.router)

# 起動時に1回だけMLモデルをロード
@app.on_event("startup")
def _startup():
    load_model()

app.include_router(plants.router)