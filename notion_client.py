import requests
from config import NOTION_TOKEN, NOTION_DATABASE_ID

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def query_database() -> list[dict]:
    """NotionデータベースのページをすべてS取得する"""
    pages = []
    payload: dict = {"page_size": 100}
    url = f"{BASE}/databases/{NOTION_DATABASE_ID}/query"
    while True:
        resp = requests.post(url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    return pages


def create_page(properties: dict) -> dict:
    """データベースに新規ページ（行）を作成する"""
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }
    resp = requests.post(f"{BASE}/pages", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def update_page(page_id: str, properties: dict) -> dict:
    """既存ページのプロパティを更新する"""
    payload = {"properties": properties}
    resp = requests.patch(f"{BASE}/pages/{page_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_users() -> list[dict]:
    """Notionワークスペースのユーザー一覧を取得する"""
    users = []
    url = f"{BASE}/users"
    params: dict = {"page_size": 100}
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        users.extend(data["results"])
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
    return users
