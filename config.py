import os
from dotenv import load_dotenv

load_dotenv()

ASANA_PAT = os.getenv("ASANA_PAT")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "69e2765b975145eb806f5a27df3b06f6")

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

# Asana Departments → Notion タグ
DEPT_TO_TAG = {
    "営業課": "営業",
    "プロダクト": "プロダクト",
    "開発": "プロダクト",
}

# Asana メンバー名 → Notion ユーザーID
# 起動時に自動構築されるが、名前が一致しない場合はここに手動で追記
USER_MAP: dict[str, str] = {
    # "岡田一輝": "notion-user-id",
    # "酒井優聖": "notion-user-id",
}
