import time
import logging

from asana_client import (
    get_subtasks_recursive,
    get_project,
    get_sections,
    get_tasks_for_section,
    get_custom_field_options,
    add_custom_field_option,
)
from notion_client import (
    create_page,
    update_page,
    archive_page,
    get_users,
    query_database_by_id,
)
from mapper import asana_to_notion_properties
from state import load_state, save_state
from config import (
    ASANA_PROJECT_GIDS,
    NOTION_DEPT_DATABASE_ID,
    ASANA_DEPT_CF_GID,
    DEPT_CATEGORY_COLOR,
    DEPT_DEFAULT_COLOR,
)

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


def sync_dept_options_to_asana(dept_page_map: dict) -> None:
    """
    Notion部門DBのトップレベル（上位DEPTなし）かつIn progressの部門を
    Asanaの「部門」カスタムフィールドの選択肢に同期する。
    新しい部門があれば追加する。
    """
    if not ASANA_DEPT_CF_GID:
        logger.warning("ASANA_DEPT_CF_GID not set, skipping dept option sync")
        return

    # Notion部門DBから全件取得してトップレベル+In progressをフィルタ
    try:
        pages = query_database_by_id(NOTION_DEPT_DATABASE_ID)
    except Exception as e:
        logger.warning(f"Failed to fetch dept DB for option sync: {e}")
        return

    notion_top_depts: set[str] = set()
    for page in pages:
        props = page.get("properties", {})
        # Status = In progress チェック
        status_prop = props.get("Status", {}).get("status")
        if not status_prop or status_prop.get("name") != "In progress":
            continue
        # 上位DEPTなし チェック
        parent_prop = props.get("上位DEPT", {}).get("relation", [])
        if parent_prop:
            continue
        # 部門名取得
        title_prop = props.get("部門名", {}).get("title", [])
        name = title_prop[0]["plain_text"] if title_prop else ""
        if name:
            notion_top_depts.add(name)

    # Asanaの現在の選択肢を取得
    try:
        existing_options = get_custom_field_options(ASANA_DEPT_CF_GID)
        existing_names = {opt["name"] for opt in existing_options}
    except Exception as e:
        logger.warning(f"Failed to fetch Asana dept options: {e}")
        return

    # 差分を追加
    to_add = notion_top_depts - existing_names
    if not to_add:
        logger.info("Dept options: all synced, nothing to add")
        return

    added = 0
    for name in sorted(to_add):
        try:
            color = DEPT_CATEGORY_COLOR.get(
                name, DEPT_DEFAULT_COLOR
            )
            add_custom_field_option(ASANA_DEPT_CF_GID, name, color)
            added += 1
            logger.info(f"  Added dept option: {name} ({color})")
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"  Failed to add dept '{name}': {e}")

    logger.info(f"Dept options sync: {added} added")


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
    valid_keys: set,
) -> tuple[int, int, int]:
    """
    サブタスクをDBの行（下位PJ）として再帰的に作成/更新する。
    何階層でも対応（上位PJ = 親タスクのNotionページID）。
    Returns (created, updated, errors)
    """
    c = u = e = 0
    for task in subtasks:
        gid = task["gid"]
        valid_keys.add(gid)
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
                    valid_keys,
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
    """
    全プロジェクトをAsanaから取得し、Notionに差分同期する。

    階層:
      Asanaプロジェクト → Notion行（最上位、上位PJなし）
        └ Asanaセクション → Notion行（上位PJ = プロジェクト）
            └ Asanaタスク → Notion行（上位PJ = セクション）
                └ サブタスク → Notion行（上位PJ = タスク、再帰）
    """
    logger.info("===== Sync started =====")
    state = load_state()
    notion_user_map = build_notion_user_map()
    dept_page_map = build_dept_map()

    # Notion部門DB → Asana部門選択肢の同期（毎回実行）
    sync_dept_options_to_asana(dept_page_map)

    created = updated = errors = archived = 0
    valid_keys: set[str] = set()

    for project_gid in ASANA_PROJECT_GIDS:
        logger.info(f"Processing project: {project_gid}")

        # ① プロジェクト自体をNotionの行として作成/更新
        try:
            project_info = get_project(project_gid)
            project_props = {
                "プロジェクト名": {
                    "title": [{
                        "text": {"content": project_info["name"]}
                    }]
                }
            }
            pj_key = f"project_{project_gid}"
            valid_keys.add(pj_key)
            pj_page_id, pj_created = _upsert_page(
                state, pj_key, project_props
            )
            if pj_created:
                created += 1
                logger.info(f"  Project created: {project_info['name']}")
            else:
                updated += 1
            time.sleep(API_WAIT)
        except Exception as e:
            logger.error(f"Project upsert failed {project_gid}: {e}")
            pj_page_id = None
            errors += 1

        # ② セクション一覧を取得
        try:
            sections = get_sections(project_gid)
        except Exception as e:
            logger.error(f"Failed to fetch sections: {e}")
            continue

        logger.info(f"  {len(sections)} sections found")

        for section in sections:
            sec_gid = section["gid"]
            sec_name = section["name"]

            # セクションをNotionの行として作成/更新
            try:
                sec_props = {
                    "プロジェクト名": {
                        "title": [{
                            "text": {"content": sec_name}
                        }]
                    }
                }
                if pj_page_id:
                    sec_props["上位PJ"] = {
                        "relation": [{"id": pj_page_id}]
                    }
                sec_key = f"section_{sec_gid}"
                valid_keys.add(sec_key)
                sec_page_id, sec_created = _upsert_page(
                    state, sec_key, sec_props
                )
                if sec_created:
                    created += 1
                    logger.info(f"  Section created: {sec_name}")
                else:
                    updated += 1
                time.sleep(API_WAIT)
            except Exception as e:
                logger.error(f"Section upsert failed: {e}")
                sec_page_id = None
                errors += 1

            # ③ セクション内のタスク取得
            try:
                tasks = get_tasks_for_section(sec_gid)
            except Exception as e:
                logger.error(
                    f"Failed to fetch tasks for section {sec_name}: {e}"
                )
                continue

            logger.info(f"    {len(tasks)} tasks in '{sec_name}'")

            for task in tasks:
                gid = task["gid"]
                valid_keys.add(gid)
                try:
                    # サブタスク再帰取得
                    task["subtasks"] = get_subtasks_recursive(gid)

                    # 上位PJ = セクション
                    props = asana_to_notion_properties(
                        task, notion_user_map, dept_page_map,
                        parent_project_page_id=sec_page_id,
                    )
                    page_id, was_created = _upsert_page(
                        state, gid, props
                    )
                    if was_created:
                        created += 1
                        logger.info(f"    Created: {task['name']}")
                    else:
                        updated += 1
                    time.sleep(API_WAIT)

                    # サブタスクを再帰的に同期
                    subtasks = task.get("subtasks", [])
                    if subtasks:
                        sc, su, se = _sync_subtasks_as_rows(
                            subtasks, page_id,
                            state, notion_user_map, dept_page_map,
                            valid_keys,
                        )
                        created += sc
                        updated += su
                        errors += se

                except Exception as e:
                    logger.error(
                        f"    Task error {gid}: {e}"
                    )
                    errors += 1

    # ④ クリーンアップ: Asanaに存在しないエントリをNotionから削除
    stale_keys = set(state.keys()) - valid_keys
    if stale_keys:
        logger.info(f"Cleanup: {len(stale_keys)} stale entries")
        for key in stale_keys:
            notion_page_id = state[key]
            try:
                archive_page(notion_page_id)
                archived += 1
                logger.info(f"  Archived: {key}")
                time.sleep(API_WAIT)
            except Exception as e:
                logger.warning(f"  Archive failed {key}: {e}")
            del state[key]

    save_state(state)
    logger.info(
        "===== Sync done: "
        f"{created} created / {updated} updated "
        f"/ {archived} archived / {errors} errors ====="
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
