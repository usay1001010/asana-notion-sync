import time
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
    resp = requests.patch(
        f"{BASE}/pages/{page_id}", headers=HEADERS, json=payload
    )
    resp.raise_for_status()
    return resp.json()


def get_block_children(block_id: str) -> list[dict]:
    """ページ/ブロックの直下の子ブロックを全件取得する"""
    children = []
    params: dict = {"page_size": 100}
    url = f"{BASE}/blocks/{block_id}/children"
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        children.extend(data["results"])
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
    return children


def delete_block(block_id: str) -> None:
    """ブロックを削除する"""
    resp = requests.delete(f"{BASE}/blocks/{block_id}", headers=HEADERS)
    resp.raise_for_status()


def clear_page_content(page_id: str) -> None:
    """ページ本文の既存ブロックをすべて削除する"""
    blocks = get_block_children(page_id)
    for block in blocks:
        delete_block(block["id"])
        time.sleep(0.2)


def append_block_children(block_id: str, children: list) -> list:
    """
    ブロックに子ブロックを追加し、作成されたブロック一覧を返す。
    Notion APIの上限（100件/リクエスト）に対応するため100件ずつバッチ処理する。
    返り値のブロックIDは呼び出し元が深い階層の再帰処理に使う。
    """
    created: list = []
    for i in range(0, max(len(children), 1), 100):
        batch = children[i:i + 100]
        if not batch:
            break
        resp = requests.patch(
            f"{BASE}/blocks/{block_id}/children",
            headers=HEADERS,
            json={"children": batch},
        )
        resp.raise_for_status()
        created.extend(resp.json().get("results", []))
        time.sleep(0.3)
    return created


def query_database_by_id(database_id: str) -> list[dict]:
    """任意のNotionデータベースのページを全件取得する"""
    pages = []
    payload: dict = {"page_size": 100}
    url = f"{BASE}/databases/{database_id}/query"
    while True:
        resp = requests.post(url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    return pages


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
