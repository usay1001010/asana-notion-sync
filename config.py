import os
from dotenv import load_dotenv

load_dotenv()

ASANA_PAT = os.getenv("ASANA_PAT")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv(
    "NOTION_DATABASE_ID", "02aaa45a3f1383a7a885811eac2644b2"
)

# 部門DBのID（DB_8_部門 — new NAGARA ワークスペース）
NOTION_DEPT_DATABASE_ID = os.getenv(
    "NOTION_DEPT_DATABASE_ID", "c15aa45a3f1383d79e1c010758a03f75"
)

# Asana「部門」カスタムフィールドのGID（multi_enum）
ASANA_DEPT_CF_GID = os.getenv("ASANA_DEPT_CF_GID", "1213664633962572")

# カンマ区切りで複数プロジェクトGIDを指定できる
ASANA_PROJECT_GIDS = [
    g.strip()
    for g in os.getenv("ASANA_PROJECT_GIDS", "").split(",")
    if g.strip()
]

# ポーリング間隔（秒）
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))

# Asana タスクの進捗 → Notion ステータス
STATUS_MAP = {
    "未着手": "未着手",
    "進行中": "進行中",
    "完了": "完了",
    "待機中": "保留",
    "延期": "保留",
    "Done": "完了",
    "In progress": "進行中",
    "Not started": "未着手",
}

# Asana Departments 名 → Notion 部門DB の部門名（完全一致しない場合の変換）
# 例: Asana "営業課" → Notion DB の "営業課" ページ
# 自動マッチングで解決できない場合のみここに追記
DEPT_NAME_MAP: dict[str, str] = {
    # "営業課": "営業課",  # 同名なら不要
}

# Asana メンバー名 → Notion ユーザーID
# 起動時に自動構築されるが、名前が一致しない場合はここに手動で追記
USER_MAP: dict[str, str] = {
    # "岡田一輝": "notion-user-id",
}

# 部門カテゴリ → Asana色
# 経営→red, 営業→orange, プロダクト開発→green, コーポレート→cool-gray
DEPT_CATEGORY_COLOR: dict[str, str] = {
    # 経営
    "経営戦略課": "red",
    "経営推進課": "red",
    "資金調達": "red",
    "外交": "red",
    # 営業
    "営業課": "orange",
    "営業戦略課": "orange",
    "CS課": "orange",
    "マーケティング": "orange",
    # プロダクト開発
    "プロダクト": "green",
    "開発": "green",
    "情報システム": "green",
    # コーポレート
    "総務": "cool-gray",
    "経理・財務": "cool-gray",
    "人事": "cool-gray",
    "労務": "cool-gray",
    "法務・知財": "cool-gray",
    "企画課": "cool-gray",
    "イベント": "cool-gray",
    "カルチャー・学び": "cool-gray",
}

# 新規部門のデフォルト色（DEPT_CATEGORY_COLORに未定義の場合）
DEPT_DEFAULT_COLOR = "none"
