import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def load_state() -> dict:
    """Asana GID → Notion page ID のマッピングを読み込む"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    """マッピングをファイルに保存する"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
