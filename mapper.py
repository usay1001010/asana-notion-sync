import re
from config import STATUS_MAP, DEPT_NAME_MAP, USER_MAP


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


def asana_to_notion_properties(
    task: dict,
    notion_user_map: dict,
    dept_page_map: dict,
) -> dict:
    """
    AsanaタスクをNotion DBのプロパティ形式に変換する

    フィールドマッピング:
        name              → プロジェクト名  (title)
        タスクの進捗       → ステータス     (select)
        start_on / Start Date → 開始日     (date)
        due_on / 期日      → 終了日         (date)
        担当者             → PM            (people)
        member            → メンバー       (people)
        notes             → 備考           (rich_text)
        Departments       → 部門           (relation → 部門DB)
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

    # 開始日 (date) — ネイティブ start_on 優先、なければ Start Date カスタムフィールド
    start_date: str | None = task.get("start_on")
    if not start_date:
        sd_raw = get_cf_value(task, "Start Date")
        if sd_raw:
            start_date = parse_japanese_date(sd_raw)
    if start_date:
        props["開始日"] = {"date": {"start": start_date}}

    # 終了日 (date) — ネイティブ due_on 優先、なければ 期日 カスタムフィールド
    end_date: str | None = task.get("due_on")
    if not end_date:
        ed_raw = get_cf_value(task, "期日")
        if ed_raw:
            end_date = parse_japanese_date(ed_raw)
    if end_date:
        props["終了日"] = {"date": {"start": end_date}}

    # PM (people) — Asana 担当者カスタムフィールド（enum・単一値）
    assignee_name = get_cf_value(task, "担当者")
    if assignee_name:
        uid = notion_user_map.get(assignee_name) or USER_MAP.get(assignee_name)
        if uid:
            props["PM"] = {"people": [{"id": uid}]}

    # メンバー (people) — Asana member カスタムフィールド（multi_enum・複数値）
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

    # 備考 (rich_text) — Asana notes（2000文字上限）
    notes = task.get("notes", "")
    if notes:
        props["備考"] = {
            "rich_text": [{"text": {"content": notes[:2000]}}]
        }

    # 部門 (relation) — Asana Departments → 部門DB のページID
    depts = get_cf_value(task, "Departments") or []
    dept_relations = []
    for dept in depts:
        # 1. config の DEPT_NAME_MAP で名前変換（手動マッピング）
        notion_name = DEPT_NAME_MAP.get(dept, dept)
        # 2. 完全一致
        page_id = dept_page_map.get(notion_name)
        # 3. 部分一致（完全一致しない場合のフォールバック）
        if not page_id:
            for db_name, db_id in dept_page_map.items():
                if notion_name in db_name or db_name in notion_name:
                    page_id = db_id
                    break
        if page_id:
            dept_relations.append({"id": page_id})
    if dept_relations:
        props["部門"] = {"relation": dept_relations}

    return props


# ステータス絵文字マップ
_STATUS_EMOJI: dict[str, str] = {
    "未着手": "⏳",
    "進行中": "🔄",
    "待機中": "⏸",
    "延期": "⏸",
    "完了": "✅",
}


def _subtask_label(task: dict) -> str:
    """サブタスク1件のトグル表示テキストを生成する"""
    if task.get("completed"):
        emoji = "✅"
    else:
        status_raw = get_cf_value(task, "タスクの進捗") or ""
        emoji = _STATUS_EMOJI.get(status_raw, "⏳")

    label = f"{emoji} {task.get('name', '(無題)')}"

    due = task.get("due_on") or ""
    if not due:
        ed_raw = get_cf_value(task, "期日") or ""
        due = parse_japanese_date(ed_raw) or ""
    if due:
        label += f"　〜{due}"

    assignee_raw = get_cf_value(task, "担当者") or ""
    if assignee_raw:
        label += f"　@{assignee_raw}"

    return label[:2000]
