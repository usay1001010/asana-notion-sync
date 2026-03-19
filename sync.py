import time
import logging

from asana_client import get_tasks, get_subtasks_recursive, get_project
from notion_client import (
    create_page,
    update_page,
    get_users,
    query_database_by_id,
)
from mapper import asana_to_notion_properties
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


def _sync_subtasks_as_rows(
    subtasks: list,
    parent_notion_page_id: str,
    state: dict,
    notion_user_map: dict,
    dept_page_map: dict,
) -> tuple[int, int, int]:
    """
    サブタスクをDBの行（下位PJ）として再帰的に作成/更新する。
    何階層でも対応（上位PJ = 親タスクのNotionページID）。
    Returns (created, updated, errors)
    """
    c = u = e = 0
    for task in subtasks:
        gid = task["gid"]
        try:
            props = asana_to_notion_properties(
                task, notion_user_map, dept_page_map,
                parent_project_page_id=parent_notion_page_id,
            )
            notion_page_id, was_created = _upsert_page(state, gid, props)
            if was_created:
                c += 1
                logger.info(f"    Created subtask: {task['name']}")
            else:
                u += 1
                logger.debug(f"    Updated subtask: {task['name']}")
            time.sleep(API_WAIT)

            child_subtasks = task.get("subtasks", [])
            if child_subtasks:
                cc, uu, ee = _sync_subtasks_as_rows(
                    child_subtasks, notion_page_id,
                    state, notion_user_map, dept_page_map,
                )
                c += cc
                u += uu
                e += ee
        except Exception as err:
            logger.error(
                f"    Error on subtask {gid} ({task.get('name')}): {err}"
            )
            e += 1
    return c, u, e


def _upsert_page(
    state: dict, key: str, props: dict
) -> tuple[str, bool]:
    """
    stateにkeyが存在すればupdate、なければcreateする。
    削除済みページへのupdateは自動的にrecreateする。
    Returns (notion_page_id, was_created)
    """
    if key in state:
        notion_page_id = state[key]
        try:
            update_page(notion_page_id, props)
            return notion_page_id, False
        except Exception as err:
            logger.warning(f"Update failed ({err}), recreating: {key}")
            del state[key]

    page = create_page(props)
    notion_page_id = page["id"]
    state[key] = notion_page_id
    return notion_page_id, True


def sync_once() -> None:
    """全プロジェクトのタスクをAsanaから取得し、Notionに差分同期する"""
    logger.info("===== Sync started =====")
    state = load_state()
    notion_user_map = build_notion_user_map()
    dept_page_map = build_dept_map()

    created = updated = errors = 0

    for project_gid in ASANA_PROJECT_GIDS:
        logger.info(f"Processing project: {project_gid}")

        # ① Asanaプロジェクト自体をNotionの行として作成/更新（最上位PJ）
        try:
            project_info = get_project(project_gid)
            project_props = {
                "プロジェクト名": {
                    "title": [{"text": {"content": project_info["name"]}}]
                }
            }
            project_state_key = f"project_{project_gid}"
            project_page_id, proj_created = _upsert_page(
                state, project_state_key, project_props
            )
            if proj_created:
                logger.info(f"  Project page created: {project_info['name']}")
                created += 1
            else:
                logger.debug(f"  Project page updated: {project_info['name']}")
                updated += 1
            time.sleep(API_WAIT)
        except Exception as e:
            logger.error(f"Failed to upsert project page {project_gid}: {e}")
            project_page_id = None
            errors += 1

        # ② タスク一覧取得
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
                # サブタスクを再帰取得（無制限の深さ・循環防止付き）
                logger.info(f"  Fetching subtasks: {task['name']}")
                task["subtasks"] = get_subtasks_recursive(gid)

                # Notionプロパティに変換（上位PJ = プロジェクト行のID）
                props = asana_to_notion_properties(
                    task, notion_user_map, dept_page_map,
                    parent_project_page_id=project_page_id,
                )

                notion_page_id, task_created = _upsert_page(state, gid, props)
                if task_created:
                    created += 1
                    logger.info(f"  Created: {task['name']}")
                else:
                    updated += 1
                    logger.debug(f"  Updated: {task['name']}")

                time.sleep(API_WAIT)

                # サブタスクをDBの行（下位PJ）として再帰的に作成/更新
                subtasks = task.get("subtasks", [])
                if subtasks:
                    sc, su, se = _sync_subtasks_as_rows(
                        subtasks, notion_page_id,
                        state, notion_user_map, dept_page_map,
                    )
                    created += sc
                    updated += su
                    errors += se
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
