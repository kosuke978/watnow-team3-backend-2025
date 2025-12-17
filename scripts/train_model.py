"""
機械学習モデル構築スクリプト (v1.0)

このスクリプトは、AIリマインダーアプリで使用する
「日次生産性スコア予測モデル」の初期バージョンを作成する。

処理フロー:
1. Task 1: ダミーデータ生成 (3000件の行動ログ)
2. Task 2: 疑似ラベル生成 (既存のスコア計算式を使用)
3. Task 3: RandomForestによるモデル学習
4. Task 4: モデル保存 (daily_score_model.pkl)
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import os

# sklearn 1.4以降ではroot_mean_squared_errorを使用
try:
    from sklearn.metrics import root_mean_squared_error
    use_new_rmse = True
except ImportError:
    use_new_rmse = False

# 乱数シード固定（再現性のため）
np.random.seed(42)

print("=" * 60)
print("機械学習モデル訓練スクリプト開始")
print("=" * 60)

# ========================================
# Task 1: ダミーデータ生成
# ========================================
print("\n[Task 1] ダミーデータ生成中...")

n_samples = 3000

# 既存の calculate_scores() に対応した特徴量を生成
data = {
    # Consistency関連
    'completed_tasks': np.random.randint(0, 11, n_samples),
    'overdue_tasks': np.random.randint(0, 6, n_samples),
    'streak_days': np.random.randint(0, 31, n_samples),
    'daily_check_in': np.random.choice([0, 1], n_samples, p=[0.2, 0.8]),
    
    # Focus関連
    'session_count': np.random.randint(0, 11, n_samples),
    'avg_session_minutes': np.random.randint(0, 121, n_samples),
    
    # Energy関連
    'wake_hour': np.random.randint(5, 13, n_samples),
    'first_action_delay_hours': np.random.uniform(0.0, 8.0, n_samples),
}

df = pd.DataFrame(data)

# completion_rate を計算
df['completion_rate'] = df.apply(
    lambda row: row['completed_tasks'] / (row['completed_tasks'] + row['overdue_tasks'])
    if (row['completed_tasks'] + row['overdue_tasks']) > 0 else 0,
    axis=1
)

print(f"生成されたデータ: {n_samples}行 x {len(df.columns)}列")
print(f"\n特徴量一覧:\n{df.columns.tolist()}")

# ========================================
# Task 2: 疑似ラベル生成
# ========================================
print("\n[Task 2] 疑似ラベル(total_score)生成中...")
print("既存の calculate_scores() ロジックを使用")

def calculate_consistency(row):
    """CONSISTENCY スコア計算"""
    return (
        40 * min(row['completed_tasks'] / 3, 1)
        + 30 * row['daily_check_in']
        + 20 * min(row['streak_days'] / 7, 1)
        + 10 * row['completion_rate']
    )

def calculate_focus(row):
    """FOCUS スコア計算"""
    return (
        60 * min(row['session_count'] / 3, 1)
        + 40 * min(row['avg_session_minutes'] / 30, 1)
    )

def calculate_energy(row):
    """ENERGY スコア計算"""
    # wake_score: 起床時間の評価
    hour = row['wake_hour']
    if 4 <= hour <= 9:
        wake_score = 100
    elif 9 < hour <= 12:
        wake_score = 50
    else:
        wake_score = 20
    
    # action_score: 初動までの時間の評価
    delay = row['first_action_delay_hours']
    if delay <= 1:
        action_score = 100
    elif delay <= 3:
        action_score = 50
    else:
        action_score = 20
    
    return 60 * (wake_score / 100) + 40 * (action_score / 100)

# 各スコアを計算
df['consistency'] = df.apply(calculate_consistency, axis=1)
df['focus'] = df.apply(calculate_focus, axis=1)
df['energy'] = df.apply(calculate_energy, axis=1)

# 総合スコア (TOTAL = 0.4*FOCUS + 0.4*CONSISTENCY + 0.2*ENERGY)
df['total_score'] = (
    0.4 * df['focus']
    + 0.4 * df['consistency']
    + 0.2 * df['energy']
)

print(f"総合スコア統計:")
print(df['total_score'].describe())

# ========================================
# Task 3: モデル学習
# ========================================
print("\n[Task 3] RandomForestRegressorによる学習中...")

# 特徴量とターゲットを分離
features = [
    'completed_tasks',
    'overdue_tasks',
    'streak_days',
    'completion_rate',
    'daily_check_in',
    'session_count',
    'avg_session_minutes',
    'wake_hour',
    'first_action_delay_hours',
]

X = df[features]
y = df['total_score']

print(f"特徴量数: {len(features)}")
print(f"特徴量: {features}")

# データ分割 (80% 学習用, 20% テスト用)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print(f"学習データ: {len(X_train)}件")
print(f"テストデータ: {len(X_test)}件")

# モデル定義と学習
model = RandomForestRegressor(
    n_estimators=200,
    max_depth=10,
    random_state=42,
    n_jobs=-1,  # 全CPUコアを使用
    verbose=1
)

print("\n学習開始...")
model.fit(X_train, y_train)
print("学習完了!")

# ========================================
# モデル評価
# ========================================
print("\n[モデル評価]")

# 訓練データでの予測
train_preds = model.predict(X_train)
if use_new_rmse:
    train_rmse = root_mean_squared_error(y_train, train_preds)
else:
    train_rmse = np.sqrt(mean_squared_error(y_train, train_preds))
train_r2 = r2_score(y_train, train_preds)

# テストデータでの予測
test_preds = model.predict(X_test)
if use_new_rmse:
    test_rmse = root_mean_squared_error(y_test, test_preds)
else:
    test_rmse = np.sqrt(mean_squared_error(y_test, test_preds))
test_r2 = r2_score(y_test, test_preds)

print(f"\n訓練データ:")
print(f"  RMSE: {train_rmse:.4f}")
print(f"  R² Score: {train_r2:.4f}")

print(f"\nテストデータ:")
print(f"  RMSE: {test_rmse:.4f}")
print(f"  R² Score: {test_r2:.4f}")

# 特徴量の重要度
feature_importance = pd.DataFrame({
    'feature': features,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(f"\n特徴量の重要度:")
print(feature_importance.to_string(index=False))

# ========================================
# Task 4: モデル保存
# ========================================
print("\n[Task 4] モデル保存中...")

# 保存先ディレクトリ
output_dir = os.path.join(os.path.dirname(__file__), '..', 'ml_models')
os.makedirs(output_dir, exist_ok=True)

# モデル保存
model_path = os.path.join(output_dir, 'daily_score_model.pkl')
joblib.dump(model, model_path)

print(f"モデルを保存しました: {model_path}")

# モデルファイルのサイズを確認
file_size = os.path.getsize(model_path) / 1024  # KB単位
print(f"ファイルサイズ: {file_size:.2f} KB")

# ========================================
# 完了
# ========================================
print("\n" + "=" * 60)
print("✓ モデル訓練スクリプト完了")
print("=" * 60)
print(f"\n出力ファイル: {model_path}")
print(f"特徴量数: {len(features)}")
print(f"テストRMSE: {test_rmse:.4f}")
print(f"テストR²: {test_r2:.4f}")
print("\n次のステップ: このモデルをAPIエンドポイントで読み込んで予測に使用できます")
