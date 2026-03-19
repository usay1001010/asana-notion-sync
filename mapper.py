import re
from config import STATUS_MAP, DEPT_TO_TAG, USER_MAP


def parse_japanese_date(s: str) -> str | None:
    """
    'YYYY年M月D日' または 'YYYY年M月D日 → YYYY年M月D日' を 'YYYY-MM-DD' に変換する
    範囲の場合は開始日を返す
    """
    if not s:
        return None
    s = s.split("→")[0].strip()
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def get_custom_field(task: dict, field_name: str) -> dict | None:
    """タスクのカスタムフィールドを名前で取得する"""
    for cf in task.get("custom_fields", []):
        if cf.get("name") == field_name:
            return cf
    return None


def get_cf_value(task: dict, field_name: str):
    """カスタムフィールドの値を取得する（型に応じてstr/list/numberを返す）"""
    cf = get_custom_field(task, field_name)
    if not cf:
        return None
    t = cf.get("type")
    if t == "enum":
        ev = cf.get("enum_value")
        return ev["name"] if ev else None
    if t == "multi_enum":
        return [v["name"] for v in cf.get("multi_enum_values", [])]
    if t == "text":
        return cf.get("text_value")
    if t == "number":
        return cf.get("number_value")
    return None


def asana_to_notion_properties(task: dict, notion_user_map: dict) -> dict:
    """
    AsanaタスクをNotion DBのプロパティ形式に変換する

    フィールドマッピング:
        name              → プロジェクト名 (title)
        タスクの進捗       → ステータス    (select)
        start_on / Start Date → 開始日    (date)
        due_on / 期日      → 終了日        (date)
        Departments       → タグ          (multi_select)
        notes             → 備考          (rich_text)
        member            → メンバー      (people)
    """
    props: dict = {}

    # プロジェクト名 (title)
    props["プロジェクト名"] = {
        "title": [{"text": {"content": task.get("name", "")}}]
    }

    # ステータス (select)
    status_raw = get_cf_value(task, "タスクの進捗")
    if task.get("completed"):
        status_raw = "完了"
    if status_raw:
        notion_status = STATUS_MAP.get(status_raw, "未着手")
        props["ステータス"] = {"select": {"name": notion_status}}

    # 開始日 (date) — ネイティブフィールド優先、なければカスタムフィールドをパース
    start_date: str | None = task.get("start_on")
    if not start_date:
        sd_raw = get_cf_value(task, "Start Date")
        if sd_raw:
            start_date = parse_japanese_date(sd_raw)
    if start_date:
        props["開始日"] = {"date": {"start": start_date}}

    # 終了日 (date) — ネイティブフィールド優先、なければカスタムフィールドをパース
    end_date: str | None = task.get("due_on")
    if not end_date:
        ed_raw = get_cf_value(task, "期日")
        if ed_raw:
            end_date = parse_japanese_date(ed_raw)
    if end_date:
        props["終了日"] = {"date": {"start": end_date}}

    # タグ (multi_select) — Departmentsをマッピング
    depts = get_cf_value(task, "Departments") or []
    tags = list({DEPT_TO_TAG[d] for d in depts if d in DEPT_TO_TAG})
    if tags:
        props["タグ"] = {"multi_select": [{"name": t} for t in tags]}

    # 備考 (rich_text) — Asanaのnotesから（2000文字上限）
    notes = task.get("notes", "")
    if notes:
        props["備考"] = {
            "rich_text": [{"text": {"content": notes[:2000]}}]
        }

    # メンバー (people) — Asana "member" カスタムフィールドから名前でマッピング
    member_names = get_cf_value(task, "member") or []
    if isinstance(member_names, str):
        member_names = [member_names]
    notion_users = []
    for name in member_names:
        uid = notion_user_map.get(name) or USER_MAP.get(name)
        if uid:
            notion_users.append({"id": uid})
    if notion_users:
        props["メンバー"] = {"people": notion_users}

    return props
