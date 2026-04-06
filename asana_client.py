import time
import requests
from config import ASANA_PAT

BASE = "https://app.asana.com/api/1.0"
HEADERS = {
    "Authorization": f"Bearer {ASANA_PAT}",
    "Accept": "application/json",
}

# タスク取得時に含めるフィールド
TASK_OPT_FIELDS = ",".join([
    "gid",
    "name",
    "notes",
    "completed",
    "due_on",
    "start_on",
    "modified_at",
    "assignee",
    "assignee.name",
    "custom_fields",
    "custom_fields.gid",
    "custom_fields.name",
    "custom_fields.type",
    "custom_fields.enum_value",
    "custom_fields.enum_value.name",
    "custom_fields.multi_enum_values",
    "custom_fields.multi_enum_values.name",
    "custom_fields.text_value",
    "custom_fields.number_value",
    "custom_fields.date_value",
    "custom_fields.people",
    "custom_fields.people.name",
])


def get_tasks(project_gid: str) -> list[dict]:
    """指定プロジェクトの全タスクを取得する（ページネーション対応）"""
    tasks = []
    params = {
        "project": project_gid,
        "opt_fields": TASK_OPT_FIELDS,
        "limit": 100,
    }
    url = f"{BASE}/tasks"
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        tasks.extend(data["data"])
        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return tasks


def get_subtasks_recursive(
    task_gid: str, visited: set | None = None
) -> list[dict]:
    """
    サブタスクを無制限に再帰取得する。

    - visited: 循環参照防止用（すでに処理したGIDのセット）
    - 各サブタスクに "subtasks" キーで子リストをネストして返す
    """
    if visited is None:
        visited = set()
    if task_gid in visited:
        return []
    visited.add(task_gid)

    subtasks = []
    params = {"opt_fields": TASK_OPT_FIELDS, "limit": 100}
    url = f"{BASE}/tasks/{task_gid}/subtasks"

    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        for task in data["data"]:
            time.sleep(0.2)  # Asana APIレート制限対策
            task["subtasks"] = get_subtasks_recursive(task["gid"], visited)
            subtasks.append(task)

        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]

    return subtasks


def get_sections(project_gid: str) -> list[dict]:
    """プロジェクトのセクション一覧を取得する"""
    sections = []
    params: dict = {"opt_fields": "gid,name", "limit": 100}
    url = f"{BASE}/projects/{project_gid}/sections"
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        sections.extend(data["data"])
        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return sections


def get_tasks_for_section(section_gid: str) -> list[dict]:
    """セクション内のタスクを全件取得する"""
    tasks = []
    params = {
        "opt_fields": TASK_OPT_FIELDS,
        "limit": 100,
    }
    url = f"{BASE}/sections/{section_gid}/tasks"
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        tasks.extend(data["data"])
        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return tasks


def get_project(project_gid: str) -> dict:
    """単一プロジェクトの情報を取得する"""
    url = f"{BASE}/projects/{project_gid}"
    params = {"opt_fields": "gid,name"}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["data"]


def get_projects(workspace_gid: str | None = None) -> list[dict]:
    """ワークスペース内のプロジェクト一覧を取得する"""
    params: dict = {"opt_fields": "gid,name", "limit": 100}
    if workspace_gid:
        params["workspace"] = workspace_gid
    url = f"{BASE}/projects"
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["data"]


def get_custom_field_options(cf_gid: str) -> list[dict]:
    """カスタムフィールドの現在の選択肢一覧を取得する"""
    url = f"{BASE}/custom_fields/{cf_gid}"
    params = {
        "opt_fields": "enum_options,enum_options.name,"
        "enum_options.enabled",
    }
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["data"].get("enum_options", [])


def add_custom_field_option(
    cf_gid: str, name: str, color: str = "none"
) -> dict:
    """カスタムフィールドに新しい選択肢を追加する"""
    url = f"{BASE}/custom_fields/{cf_gid}/enum_options"
    payload = {
        "data": {"name": name, "enabled": True, "color": color}
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()["data"]
