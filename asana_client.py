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


def get_projects(workspace_gid: str | None = None) -> list[dict]:
    """ワークスペース内のプロジェクト一覧を取得する"""
    params: dict = {"opt_fields": "gid,name", "limit": 100}
    if workspace_gid:
        params["workspace"] = workspace_gid
    url = f"{BASE}/projects"
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["data"]
