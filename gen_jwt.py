from jose import jwt
import time
import os
from dotenv import load_dotenv

# .env 読み込み
load_dotenv()

SECRET = os.getenv("SUPABASE_JWT_SECRET")

# Supabase のユーザーID（さっきの Raw JSON の id）
USER_ID = "70d777cd-f959-435a-8f95-0209512c83b9"

payload = {
    "sub": USER_ID,            # 認証ユーザーID
    "role": "authenticated",   # Supabase の標準ロール
    "exp": int(time.time()) + 60 * 60 * 24  # 24時間有効
}

token = jwt.encode(payload, SECRET, algorithm="HS256")
print(token)