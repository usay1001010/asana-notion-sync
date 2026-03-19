import time
import logging

from asana_client import get_tasks
from notion_client import create_page, update_page, get_users
from mapper import asana_to_notion_properties
from state import load_state, save_state
from config import ASANA_PROJECT_GIDS

logger = logging.getLogger(__name__)

# Notion APIレート制限対策（リクエスト間のウェイト）
API_WAIT = 0.35


def build_notion_user_map() -> dict:
    """
    Notionのユーザー一覧を取得して 名前 → user_id の辞書を返す
    Asanaのカスタムフィールド "member" の名前と突き合わせるために使う
    """
    user_map: dict[str, str] = {}
    try:
        users = get_users()
        for u in users:
            if u.get("type") == "person":
                name = u.get("name", "")
                if name:
                    user_map[name] = u["id"]
        logger.info(f"Notion users loaded: {list(user_map.keys())}")
    except Exception as e:
        logger.warning(f"Failed to fetch Notion users: {e}")
    return user_map


def sync_once() -> None:
    """全プロジェクトのタスクをAsanaから取得し、Notionに差分同期する"""
    logger.info("===== Sync started =====")
    state = load_state()  # {asana_gid: notion_page_id}
    notion_user_map = build_notion_user_map()

    created = updated = errors = 0

    for project_gid in ASANA_PROJECT_GIDS:
        logger.info(f"Fetching tasks: project={project_gid}")
        try:
            tasks = get_tasks(project_gid)
        except Exception as e:
            logger.error(f"Failed to fetch tasks for project {project_gid}: {e}")
            continue

        logger.info(f"  {len(tasks)} tasks found")

        for task in tasks:
            gid = task["gid"]
            try:
                props = asana_to_notion_properties(task, notion_user_map)

                if gid in state:
                    # 既存ページを更新
                    update_page(state[gid], props)
                    updated += 1
                    logger.debug(f"  Updated: {task['name']}")
                else:
                    # 新規ページを作成
                    page = create_page(props)
                    state[gid] = page["id"]
                    created += 1
                    logger.info(f"  Created: {task['name']}")

                time.sleep(API_WAIT)

            except Exception as e:
                logger.error(f"  Error on task {gid} ({task.get('name')}): {e}")
                errors += 1

    save_state(state)
    logger.info(
        f"===== Sync done: {created} created / {updated} updated / {errors} errors ====="
    )


def run_forever(interval: int = 300) -> None:
    """指定間隔（秒）でsync_onceを繰り返す"""
    while True:
        try:
            sync_once()
        except Exception as e:
            logger.error(f"Unexpected error in sync: {e}")
        logger.info(f"Next sync in {interval}s...")
        time.sleep(interval)
