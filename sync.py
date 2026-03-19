import time
import logging

from asana_client import get_tasks, get_subtasks_recursive
from notion_client import (
    create_page,
    update_page,
    get_users,
    get_block_children,
    clear_page_content,
    append_block_children,
    query_database_by_id,
)
from mapper import asana_to_notion_properties, _subtask_label
from state import load_state, save_state
from config import ASANA_PROJECT_GIDS, NOTION_DEPT_DATABASE_ID

logger = logging.getLogger(__name__)

API_WAIT = 0.35


def build_dept_map() -> dict:
    """
    部門DB（DB_8_部門）を取得して 部門名 → Notion page_id の辞書を返す。
    Asana Departments の値と突き合わせて relation を設定するために使う。
    """
    dept_map: dict[str, str] = {}
    try:
        pages = query_database_by_id(NOTION_DEPT_DATABASE_ID)
        for page in pages:
            title_prop = page.get("properties", {}).get("部門名", {})
            titles = title_prop.get("title", [])
            name = titles[0]["plain_text"] if titles else ""
            if name:
                dept_map[name] = page["id"]
        logger.info(f"Notion dept map loaded: {list(dept_map.keys())}")
    except Exception as e:
        logger.warning(f"Failed to fetch dept map: {e}")
    return dept_map


def build_notion_user_map() -> dict:
    """Notionユーザー一覧を取得して 名前 → user_id の辞書を返す"""
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


def _build_toggle(task: dict, include_children: bool = True) -> dict:
    """タスク1件分のトグルブロックを生成する（children は1階層まで）"""
    block: dict = {
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {"type": "text", "text": {"content": _subtask_label(task)}}
            ],
        },
    }
    if include_children:
        child_tasks = task.get("subtasks", [])
        if child_tasks:
            # Notion API 制限: 1リクエストで2階層まで → ここでは直下1層のみ含める
            block["toggle"]["children"] = [
                {
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": _subtask_label(c)},
                            }
                        ],
                    },
                }
                for c in child_tasks
            ]
    return block


def _sync_subtask_blocks(parent_block_id: str, subtasks: list) -> None:
    """
    サブタスクを無制限の深さでNotionにトグルブロックとして書き込む。

    Notion APIは1リクエストで2階層（親＋直下の子）まで対応。
    それより深い階層は、作成済みブロックのIDを取得してから再帰的に追加する。

    [アルゴリズム]
    1. 現在階層 + 1階層下の子を含むブロックを送信
    2. レスポンスで作成ブロックIDを取得
    3. 各ブロックの子IDを取得し、さらに深い孫以降を再帰的に送信
    """
    if not subtasks:
        return

    # Level N + Level N+1 を構築して送信
    level_blocks = [_build_toggle(t, include_children=True) for t in subtasks]
    created = append_block_children(parent_block_id, level_blocks)

    # Level N+2 以降を再帰処理
    for i, task in enumerate(subtasks):
        child_tasks = task.get("subtasks", [])
        if not child_tasks or i >= len(created):
            continue

        # Level N+1 ブロックのIDを取得（さっき作った直下の子）
        level_n1_block_id = created[i]["id"]
        level_n1_children = get_block_children(level_n1_block_id)
        time.sleep(0.2)

        for j, child_task in enumerate(child_tasks):
            grandchild_tasks = child_task.get("subtasks", [])
            if not grandchild_tasks or j >= len(level_n1_children):
                continue

            level_n2_block_id = level_n1_children[j]["id"]
            # 再帰 → Level N+2, N+3, ... を処理
            _sync_subtask_blocks(level_n2_block_id, grandchild_tasks)
            time.sleep(0.2)


def sync_once() -> None:
    """全プロジェクトのタスクをAsanaから取得し、Notionに差分同期する"""
    logger.info("===== Sync started =====")
    state = load_state()
    notion_user_map = build_notion_user_map()
    dept_page_map = build_dept_map()

    created = updated = errors = 0

    for project_gid in ASANA_PROJECT_GIDS:
        logger.info(f"Fetching tasks: project={project_gid}")
        try:
            tasks = get_tasks(project_gid)
        except Exception as e:
            logger.error(
                f"Failed to fetch tasks for project {project_gid}: {e}"
            )
            continue

        logger.info(f"  {len(tasks)} tasks found")

        for task in tasks:
            gid = task["gid"]
            try:
                # ① サブタスクを再帰取得（無制限の深さ・循環防止付き）
                logger.info(f"  Fetching subtasks: {task['name']}")
                task["subtasks"] = get_subtasks_recursive(gid)

                # ② Notionプロパティに変換してページ作成/更新
                props = asana_to_notion_properties(
                    task, notion_user_map, dept_page_map
                )

                if gid in state:
                    notion_page_id = state[gid]
                    try:
                        update_page(notion_page_id, props)
                        updated += 1
                        logger.debug(f"  Updated: {task['name']}")
                    except Exception as update_err:
                        logger.warning(
                            f"  Update failed ({update_err}), recreating: {task['name']}"
                        )
                        del state[gid]
                        page = create_page(props)
                        notion_page_id = page["id"]
                        state[gid] = notion_page_id
                        created += 1
                        logger.info(f"  Recreated: {task['name']}")
                else:
                    page = create_page(props)
                    notion_page_id = page["id"]
                    state[gid] = notion_page_id
                    created += 1
                    logger.info(f"  Created: {task['name']}")

                time.sleep(API_WAIT)

                # ③ ページ本文を一旦クリアして、サブタスクを再帰的に書き込む
                subtasks = task.get("subtasks", [])
                clear_page_content(notion_page_id)
                if subtasks:
                    _sync_subtask_blocks(notion_page_id, subtasks)
                    logger.info(
                        f"  Subtasks synced: {len(subtasks)} top-level"
                    )

            except Exception as e:
                logger.error(
                    f"  Error on task {gid} ({task.get('name')}): {e}"
                )
                errors += 1

    save_state(state)
    logger.info(
        "===== Sync done: "
        f"{created} created / {updated} updated / {errors} errors ====="
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
