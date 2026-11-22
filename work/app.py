from __future__ import annotations

import html
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import streamlit as st
from streamlit_sortables import sort_items

from team_scheduler.aggregate import aggregate_notifications
from team_scheduler.replan import replan_plan
from workspace_store import (
    delete_ddl_status,
    delete_notice,
    get_ddl_status,
    list_ddl_statuses,
    list_notices,
    save_notice,
    update_ddl_status,
    update_status,
)
from mock_engine import (
    SAMPLE_CASES,
    WORKFLOW_STEPS,
    build_plan,
    generate_ics,
)
from model_provider import environment_defaults, parse_notice


APP_TIMEZONE = timezone(timedelta(hours=8))


st.set_page_config(
    page_title="DDL 急救站 · 三步急救",
    page_icon="🚑",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_VERSION = "v0.7-guided"
if st.session_state.get("app_version") != APP_VERSION:
    st.session_state.clear()
    st.session_state.app_version = APP_VERSION
if "reward_xp" not in st.session_state:
    st.session_state.reward_xp = 0
if "reward_completed_count" not in st.session_state:
    st.session_state.reward_completed_count = 0
if "reward_streak" not in st.session_state:
    st.session_state.reward_streak = 0
if "last_reward_points" not in st.session_state:
    st.session_state.last_reward_points = 0
if "reward_claimed_keys" not in st.session_state:
    st.session_state.reward_claimed_keys = []

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&display=swap');
html, body, [class*="css"] {
    font-family: 'Noto Sans SC', sans-serif;
}
.stApp {
    background:
        radial-gradient(circle at 12% 8%, rgba(249, 115, 22, .12), transparent 28%),
        radial-gradient(circle at 88% 12%, rgba(37, 99, 235, .12), transparent 30%),
        linear-gradient(135deg, #f8fafc 0%, #eef2ff 50%, #fff7ed 100%);
}
.block-container {
    max-width: 1180px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}
.hero {
    border: 1px solid rgba(15, 23, 42, .08);
    border-radius: 28px;
    padding: 2rem 2.1rem;
    background: rgba(255,255,255,.78);
    box-shadow: 0 24px 60px rgba(15, 23, 42, .08);
    backdrop-filter: blur(12px);
    margin-bottom: 1.2rem;
}
.hero h1 {
    margin: .35rem 0 .4rem;
    font-size: clamp(2.2rem, 5vw, 4.3rem);
    letter-spacing: -.055em;
    color: #0f172a;
}
.hero p {
    margin: 0;
    color: #475569;
    font-size: 1.05rem;
}
.badge {
    display: inline-block;
    padding: .32rem .7rem;
    border-radius: 999px;
    background: #fff7ed;
    color: #c2410c;
    border: 1px solid #fed7aa;
    font-size: .78rem;
    font-weight: 800;
    letter-spacing: .04em;
}
.trust-banner {
    border: 1px solid #bbf7d0;
    background: linear-gradient(135deg, #f0fdf4, #ffffff);
    color: #166534;
    border-radius: 16px;
    padding: .8rem .95rem;
    margin: .75rem 0 1rem;
    font-size: .88rem;
    line-height: 1.6;
}
.board-heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: .75rem;
    margin: 1.35rem 0 .65rem;
}
.board-heading h3 {
    margin: 0;
    color: #0f172a;
    letter-spacing: -.02em;
}
.board-heading span {
    color: #64748b;
    font-size: .78rem;
}
.ddl-card {
    border: 1px solid rgba(15, 23, 42, .08);
    border-radius: 20px;
    padding: 1rem 1.05rem;
    background: rgba(255,255,255,.94);
    box-shadow: 0 12px 30px rgba(15, 23, 42, .055);
    margin: .7rem 0;
}
.ddl-card-head {
    display: flex;
    justify-content: space-between;
    gap: .75rem;
    align-items: flex-start;
}
.ddl-card h4 {
    margin: 0 0 .25rem;
    color: #0f172a;
    font-size: 1.05rem;
    line-height: 1.4;
}
.ddl-card p {
    margin: .15rem 0;
    color: #475569;
    font-size: .88rem;
    line-height: 1.55;
}
.pill {
    display: inline-block;
    white-space: nowrap;
    border-radius: 999px;
    padding: .25rem .58rem;
    font-size: .72rem;
    font-weight: 800;
    letter-spacing: .02em;
}
.pill-primary { color: #1d4ed8; background: #dbeafe; }
.pill-warn { color: #b45309; background: #fef3c7; }
.pill-muted { color: #475569; background: #f1f5f9; }
.pill-done { color: #166534; background: #dcfce7; }
.pill-danger { color: #b91c1c; background: #fee2e2; }
.workspace-empty {
    border: 1px dashed #cbd5e1;
    border-radius: 18px;
    padding: 1rem 1.1rem;
    background: rgba(255,255,255,.65);
    color: #64748b;
    margin: .5rem 0 1rem;
}
.tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem;
    margin: .7rem 0 .55rem;
}
.tag {
    display: inline-block;
    border-radius: 999px;
    padding: .2rem .5rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    color: #475569;
    font-size: .72rem;
}
.ddl-action {
    margin-top: .55rem;
    color: #2563eb;
    font-size: .8rem;
    font-weight: 800;
}
.card {
    border: 1px solid rgba(15, 23, 42, .08);
    border-radius: 20px;
    padding: 1rem 1.1rem;
    background: rgba(255,255,255,.82);
    box-shadow: 0 12px 32px rgba(15, 23, 42, .05);
    margin: .45rem 0 .75rem;
}
@media (max-width: 768px) {
    .block-container { max-width: 100%; padding: .65rem .45rem 1.5rem; }
    .hero { padding: 1.05rem 1rem; border-radius: 18px; margin-bottom: .75rem; }
    .hero h1 { font-size: 1.95rem; line-height: 1.12; letter-spacing: -.04em; }
    .hero p { font-size: .92rem; }
    .badge { font-size: .65rem; }
    .board-heading { flex-direction: column; align-items: flex-start; gap: .2rem; margin: 1rem 0 .5rem; }
    .board-heading h3 { font-size: 1.25rem; }
    .board-heading span { font-size: .72rem; }
    .ddl-card { padding: .82rem; border-radius: 16px; margin: .55rem 0; }
    .ddl-card-head { flex-direction: column; gap: .35rem; }
    .ddl-card h4 { font-size: 1rem; }
    .ddl-card p { font-size: .82rem; line-height: 1.5; }
    .tag-row { gap: .25rem; margin: .55rem 0 .45rem; }
    .tag { font-size: .66rem; padding: .18rem .42rem; }
    .stButton > button { min-height: 2.55rem; font-size: .82rem; }
    .stTextInput input, .stTextArea textarea { font-size: 16px !important; }
    div[data-testid="stHorizontalBlock"] { gap: .3rem; }
    div[data-testid="column"] { min-width: 0; }
    [data-testid="stMetric"] { padding: .35rem .4rem; }
    [data-testid="stMetricValue"] { font-size: 1.25rem; overflow-wrap: anywhere; }
    [data-testid="stMetricLabel"] { font-size: .7rem; }
    [data-baseweb="tab-list"] { overflow-x: auto; white-space: nowrap; }
    [data-baseweb="tab"] { font-size: .78rem; padding-left: .45rem; padding-right: .45rem; }
}
@media (max-width: 420px) {
    .hero h1 { font-size: 1.72rem; }
    .ddl-card h4 { font-size: .95rem; }
    .stButton > button { font-size: .78rem; }
}
.card h4 {
    margin: 0 0 .3rem;
    color: #0f172a;
}
.card p {
    margin: .2rem 0;
    color: #475569;
    line-height: 1.65;
}
.task {
    border-left: 5px solid #2563eb;
    border-radius: 14px;
    padding: .8rem 1rem;
    background: #fff;
    margin: .5rem 0;
    box-shadow: 0 8px 22px rgba(15, 23, 42, .045);
}
.task b {
    color: #0f172a;
}
.task small {
    color: #64748b;
    margin-left: .45rem;
}
.task p {
    margin: .25rem 0 0;
    color: #475569;
    font-size: .92rem;
}
.level-card {
    border: 1px solid rgba(15, 23, 42, .08);
    border-radius: 18px;
    padding: 1rem 1rem 1.1rem;
    background: #fff;
    box-shadow: 0 10px 26px rgba(15, 23, 42, .05);
    min-height: 185px;
    height: 100%;
}
.level-card .level-tag {
    display: inline-block;
    padding: .22rem .55rem;
    border-radius: 999px;
    font-size: .72rem;
    font-weight: 900;
    letter-spacing: .04em;
    margin-bottom: .55rem;
}
.level-card h4 {
    margin: 0 0 .4rem;
    color: #0f172a;
    line-height: 1.35;
}
.level-card p {
    margin: .25rem 0;
    color: #475569;
    font-size: .9rem;
    line-height: 1.55;
}
.level-minimum { border-top: 6px solid #22c55e; }
.level-standard { border-top: 6px solid #3b82f6; }
.level-stretch { border-top: 6px solid #f59e0b; }
.big-first {
    border: 2px solid #86efac;
    border-radius: 26px;
    padding: 1.6rem 1.7rem;
    background: linear-gradient(135deg, #f0fdf4, #ffffff);
    box-shadow: 0 20px 50px rgba(22, 101, 52, .10);
    margin: .5rem 0 1rem;
}
.big-first h2 {
    margin: .5rem 0 .6rem;
    color: #14532d;
    font-size: clamp(1.35rem, 3vw, 2.2rem);
    line-height: 1.35;
    letter-spacing: -.02em;
}
.big-first p {
    margin: 0;
    color: #166534;
}
.workflow {
    display: flex;
    flex-wrap: wrap;
    gap: .4rem;
    margin: .4rem 0 .8rem;
}
.workflow span {
    padding: .34rem .58rem;
    background: #eef2ff;
    color: #3730a3;
    border-radius: 999px;
    font-size: .75rem;
    font-weight: 700;
}
.stButton > button {
    border-radius: 12px;
    font-weight: 700;
}
</style>
""",
    unsafe_allow_html=True,
)

if "parsed" not in st.session_state:
    st.session_state.parsed = None
if "plan" not in st.session_state:
    st.session_state.plan = None
if "started" not in st.session_state:
    st.session_state.started = False
if "completed" not in st.session_state:
    st.session_state.completed = False
if "stuck" not in st.session_state:
    st.session_state.stuck = False
if "replan" not in st.session_state:
    st.session_state.replan = None
if "remaining_minutes" not in st.session_state:
    st.session_state.remaining_minutes = 15
if "current_record_id" not in st.session_state:
    st.session_state.current_record_id = None
if "workspace_plan" not in st.session_state:
    st.session_state.workspace_plan = None
if "workspace_aggregated" not in st.session_state:
    st.session_state.workspace_aggregated = None
if "workspace_plan_stale" not in st.session_state:
    st.session_state.workspace_plan_stale = False
if "delete_confirm_id" not in st.session_state:
    st.session_state.delete_confirm_id = None
if "post_save_hint" not in st.session_state:
    st.session_state.post_save_hint = False

EDITOR_KEYS = ["title_input", "deadline_input", "deliverables_input", "materials_input"]


def clear_editor_keys() -> None:
    for key in EDITOR_KEYS:
        st.session_state.pop(key, None)


def deadline_to_iso(value: str) -> str | None:
    """Keep edited deadline and .ics deadline in sync."""
    value = (value or "").strip()
    if not value or "待确认" in value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=APP_TIMEZONE).isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=APP_TIMEZONE)
        return parsed.astimezone(APP_TIMEZONE).isoformat()
    except ValueError:
        return None


def normalize_plan(plan: dict) -> dict:
    """Keep the UI stable when an older session plan is still in memory."""
    plan.setdefault(
        "today_deliverable",
        plan.get("today_task_title") or plan.get("today_first_step") or "完成今天这一块",
    )
    plan.setdefault(
        "today_warm_start",
        plan.get("today_first_step") or "打开任务要求，先找到第一题。",
    )
    plan.setdefault("today_done_definition", "完成这一块，并留下可见成果。")
    if "today_levels" not in plan:
        minimum_deliverable = plan["today_deliverable"]
        minimum_minutes = plan.get("today_minutes", 30)
        minimum_done = plan["today_done_definition"]
        plan["today_levels"] = {
            "minimum": {
                "label": "保底",
                "deliverable": minimum_deliverable,
                "minutes": minimum_minutes,
                "done_definition": minimum_done,
            },
            "standard": {
                "label": "进阶",
                "deliverable": f"{minimum_deliverable}，并完成一次自查",
                "minutes": minimum_minutes + 5,
                "done_definition": f"{minimum_done}，并检查是否符合要求。",
            },
            "stretch": {
                "label": "挑战",
                "deliverable": f"{minimum_deliverable}，再向前多做一步",
                "minutes": minimum_minutes + 15,
                "done_definition": f"{minimum_done}，并留下一个额外的延伸成果。",
            },
        }
    for task in plan.get("tasks", []):
        task.setdefault("warm_start", task.get("first_step") or "打开任务要求。")
        task.setdefault("done_definition", "完成这个任务块。")
    return plan


STATUS_META = {
    "pending": ("接下来", "pill-muted"),
    "reopened": ("接下来", "pill-muted"),
    "primary": ("今日主攻", "pill-primary"),
    "active": ("进行中", "pill-warn"),
    "done": ("已完成", "pill-done"),
    "stuck": ("卡住", "pill-danger"),
    "expired": ("已过期", "pill-danger"),
}


def _deadline_iso_from_item(item: dict) -> str:
    deadline = item.get("deadline")
    if isinstance(deadline, dict):
        value = deadline.get("normalized") or deadline.get("deadline_iso")
        if value:
            return str(value)
    return str(item.get("deadline_iso") or "")


def _parse_deadline_value(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed


def _record_deadlines(record: dict) -> list[str]:
    parsed = record.get("parsed") or {}
    values = [
        _deadline_iso_from_item(item)
        for item in (parsed.get("ddl_items") or [])
        if isinstance(item, dict)
    ]
    values = [value for value in values if value]
    if not values and parsed.get("deadline_iso"):
        values = [str(parsed["deadline_iso"])]
    return values


def _record_deadline(record: dict) -> str:
    values = _record_deadlines(record)
    if not values:
        return ""
    return min(values, key=lambda value: _parse_deadline_value(value) or datetime.max.replace(tzinfo=APP_TIMEZONE))


def _record_is_expired(record: dict, now: datetime | None = None) -> bool:
    values = _record_deadlines(record)
    if not values:
        return False
    current = now or datetime.now(APP_TIMEZONE)
    return all(
        (parsed := _parse_deadline_value(value)) is not None and parsed < current
        for value in values
    )


def _active_parsed(record: dict, now: datetime | None = None) -> dict | None:
    """返回只含未过期 DDL 的 parsed 副本；全部过期时返回 None。"""
    current = now or datetime.now(APP_TIMEZONE)
    parsed = deepcopy(record.get("parsed") or {})
    items = parsed.get("ddl_items") or []
    if items:
        active_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = _deadline_iso_from_item(item)
            deadline = _parse_deadline_value(value) if value else None
            if deadline is not None and deadline < current:
                continue
            active_items.append(item)
        if not active_items:
            return None
        parsed["ddl_items"] = active_items
        values = [_deadline_iso_from_item(item) for item in active_items]
        values = [value for value in values if value]
        if values:
            parsed["deadline_iso"] = min(
                values,
                key=lambda value: _parse_deadline_value(value) or datetime.max.replace(tzinfo=APP_TIMEZONE),
            )
        return parsed
    return None if _record_is_expired(record, current) else parsed


def _record_summary(record: dict) -> tuple[str, int]:
    parsed = record.get("parsed") or {}
    items = parsed.get("ddl_items") or []
    deadline = _record_deadline(record) or "待确认"
    ddl_count = len(items) if items else (1 if parsed.get("deadline_iso") else 0)
    task_count = sum(len(item.get("tasks") or []) for item in items)
    if not task_count:
        task_count = len(parsed.get("deliverables") or [])
    return str(deadline), max(ddl_count, 0) if task_count else ddl_count


def _format_ddl_deadline(item: dict) -> str:
    value = _deadline_iso_from_item(item)
    parsed = _parse_deadline_value(value)
    return parsed.strftime("%m月%d日 %H:%M") if parsed else "截止待确认"


def _record_ddl_items(record: dict) -> list[dict]:
    parsed = record.get("parsed") or {}
    items = [item for item in (parsed.get("ddl_items") or []) if isinstance(item, dict)]
    if items:
        return items
    tasks = [
        {"id": f"T{index}", "title": str(title), "dependency": []}
        for index, title in enumerate(parsed.get("deliverables") or [], 1)
    ]
    return [{
        "id": str(parsed.get("ddl_id") or "DDL1"),
        "title": str(parsed.get("title") or "未命名 DDL"),
        "deadline": parsed.get("deadline"),
        "deadline_iso": parsed.get("deadline_iso"),
        "deliverables": parsed.get("deliverables") or [],
        "tasks": tasks,
    }]


def _ddl_status_for(record: dict, ddl_id: str) -> tuple[str, bool]:
    row = get_ddl_status(record["id"], ddl_id)
    if row:
        return str(row["status"]), True
    return str(record.get("status") or "pending"), False


def _sync_notice_status(record_id: str) -> None:
    rows = list_ddl_statuses(record_id)
    if not rows:
        return
    statuses = {str(row.get("status")) for row in rows}
    if statuses == {"done"}:
        update_status(record_id, "done")
    elif "stuck" in statuses:
        update_status(record_id, "stuck")
    elif "active" in statuses:
        update_status(record_id, "active")
    elif "reopened" in statuses:
        update_status(record_id, "reopened")
    else:
        update_status(record_id, "pending")


def _ddl_reward_points(record: dict, ddl_id: str) -> int:
    for item in (record.get("parsed") or {}).get("ddl_items") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == str(ddl_id):
            return {"保底": 20, "进阶": 40, "挑战": 60}.get(str(item.get("target_level") or "保底"), 20)
    return 20


def _apply_ddl_status(record: dict, ddl_id: str, status: str, has_ddl_row: bool) -> None:
    if status == "done":
        points = _ddl_reward_points(record, ddl_id)
        grant_reward(
            points,
            f"workspace:{record['id']}:{ddl_id}",
            reason="完成任务",
            celebrate=True,
        )
    if has_ddl_row:
        update_ddl_status(record["id"], ddl_id, status)
        _sync_notice_status(record["id"])
    else:
        # 兼容没有 parsed.ddl_items 的旧单 DDL 通知。
        update_status(record["id"], status)
    st.session_state.delete_confirm_id = None
    if st.session_state.get("workspace_plan") or st.session_state.get("workspace_aggregated"):
        st.session_state.workspace_plan_stale = True


def _active_parsed_for_ddl(record: dict, now: datetime) -> dict | None:
    parsed = deepcopy(record.get("parsed") or {})
    active_items: list[dict] = []
    for item in _record_ddl_items(record):
        ddl_id = str(item.get("id") or "DDL1")
        status, _ = _ddl_status_for(record, ddl_id)
        if status == "done":
            continue
        deadline = _parse_deadline_value(_deadline_iso_from_item(item))
        if deadline is not None and deadline < now:
            continue
        active_items.append(item)
    if not active_items:
        return None
    parsed["ddl_items"] = active_items
    values = [_deadline_iso_from_item(item) for item in active_items]
    values = [value for value in values if value]
    if values:
        parsed["deadline_iso"] = min(
            values,
            key=lambda value: _parse_deadline_value(value) or datetime.max.replace(tzinfo=APP_TIMEZONE),
        )
    return parsed


def _build_ddl_cards(records: list[dict], now: datetime) -> list[dict]:
    cards: list[dict] = []
    for record in records:
        items = _record_ddl_items(record)
        for index, item in enumerate(items):
            ddl_id = str(item.get("id") or f"DDL{index + 1}")
            status, has_ddl_row = _ddl_status_for(record, ddl_id)
            # 兼容旧数据中把 primary 当状态写入的记录；MVP 只把它作为显示态。
            if status == "primary":
                status = "pending"
            deadline = _parse_deadline_value(_deadline_iso_from_item(item))
            expired = status != "done" and deadline is not None and deadline < now
            cards.append({
                "record": record,
                "item": item,
                "ddl_id": ddl_id,
                "status": status,
                "has_ddl_row": has_ddl_row,
                "expired": expired,
                "is_first": index == 0,
                "card_count": len(items),
            })
    candidates = [
        card for card in cards
        if card["status"] == "pending" and not card["expired"]
    ]
    primary = min(
        candidates,
        key=lambda card: _deadline_iso_from_item(card["item"]) or "9999-12-31T23:59:59",
        default=None,
    )
    for card in cards:
        if card is primary:
            card["display_status"] = "primary"
        elif card["expired"]:
            card["display_status"] = "expired"
        else:
            card["display_status"] = card["status"]
    cards.sort(
        key=lambda card: (
            0 if card["display_status"] == "primary" else 1,
            _deadline_iso_from_item(card["item"]) or "9999-12-31T23:59:59",
            str(card["record"].get("title") or ""),
            card["ddl_id"],
        )
    )
    return cards



def _next_step_message(cards: list[dict], plan_stale: bool = False) -> str:
    active = [card for card in cards if card["status"] == "active" and not card["expired"]]
    pending = [card for card in cards if card["status"] == "pending" and not card["expired"]]
    stuck = [card for card in cards if card["status"] == "stuck"]
    if plan_stale:
        return "下一步：先重新生成全工作台今日计划；卡住的 DDL 可以重新打开后再排期。"
    if active:
        return f"下一步：继续「{active[0]['item'].get('title', '进行中的 DDL')}」；其他卡可稍后再处理。"
    if pending:
        return f"下一步：从「{pending[0]['item'].get('title', '今日主攻')}」点“开始”。"
    if stuck:
        return f"下一步：「{stuck[0]['item'].get('title', '卡住的 DDL')}」已卡住，请重新打开或重新生成计划。"
    if cards and all(card["status"] == "done" for card in cards):
        return "下一步：所有 DDL 已完成，可以查看成果或删除旧通知。"
    return "下一步：查看卡住的 DDL，重新打开或重新生成计划。"

def delete_ddl_task(record_id: str, ddl_id: str) -> None:
    record = next((item for item in list_notices() if item.get("id") == record_id), None)
    if not record:
        return
    parsed = deepcopy(record.get("parsed") or {})
    remaining = [
        item for item in parsed.get("ddl_items") or []
        if isinstance(item, dict) and str(item.get("id") or "") != str(ddl_id)
    ]
    if not remaining:
        delete_notice(record_id)
    else:
        parsed["ddl_items"] = remaining
        parsed["deliverables"] = [str(item.get("title") or "任务") for item in remaining]
        deadlines = [
            item.get("deadline_iso") or (item.get("deadline") or {}).get("normalized")
            for item in remaining
        ]
        deadlines = [value for value in deadlines if value]
        parsed["deadline_iso"] = min(deadlines) if deadlines else None
        parsed["schedule_ready"] = bool(deadlines)
        if deadlines:
            parsed["deadline"] = datetime.fromisoformat(parsed["deadline_iso"]).strftime("%Y-%m-%d %H:%M")
        else:
            parsed["deadline"] = "待确认"
        save_notice(parsed, raw_text=record.get("raw_text"), record_id=record_id)
        delete_ddl_status(record_id, ddl_id)
    if st.session_state.get("current_record_id") == record_id and st.session_state.get("parsed"):
        st.session_state.parsed = deepcopy(parsed)
    st.session_state.workspace_plan_stale = True
    st.session_state.workspace_delete_ddl_confirm = None
    st.toast("任务已删除，其他任务保留")


def load_record_for_edit(record_id: str) -> None:
    record = next((item for item in list_notices() if item.get("id") == record_id), None)
    if not record:
        return
    st.session_state.notice_text = record.get("raw_text") or record.get("parsed", {}).get("raw_text") or ""
    st.session_state.parsed = deepcopy(record.get("parsed") or {})
    st.session_state.plan = None
    st.session_state.started = False
    st.session_state.completed = False
    st.session_state.stuck = False
    st.session_state.replan = None
    st.session_state.current_record_id = record["id"]
    st.session_state.guided_section = "急救流程"


def render_workspace(draggable: bool = False) -> None:
    records = list_notices()
    if not records:
        st.markdown(
            '<div class="workspace-empty"><b>我的 DDL 工作台还是空的。</b><br>先粘贴一条通知，解析后点“保存到工作台”。保存过的通知会跨刷新保留。</div>',
            unsafe_allow_html=True,
        )
        return

    now = datetime.now(APP_TIMEZONE)
    cards = _build_ddl_cards(records, now)
    expired_cards = [card for card in cards if card["expired"]]
    st.markdown(
        f'<div class="board-heading"><h3>我的 DDL 工作台</h3><span>已保存 {len(records)} 条通知 · {len(cards)} 个独立 DDL</span></div>',
        unsafe_allow_html=True,
    )
    if expired_cards:
        st.caption(f"已跳过 {len(expired_cards)} 个过期 DDL；它们仍保留在工作台，请单独确认或删除。")

    if draggable and cards:
        saved_order = list(st.session_state.get("workspace_drag_order") or [])
        if saved_order:
            by_key = {f"{card['record']['id']}::{card['ddl_id']}": card for card in cards}
            reordered = [by_key[key] for key in saved_order if key in by_key]
            reordered.extend(card for card in cards if card not in reordered)
            cards = reordered

        labels: list[str] = []
        label_to_card: dict[str, dict] = {}
        counts: dict[str, int] = {}
        for card in cards:
            title = str(card["item"].get("title") or "未命名任务")
            deadline = _format_ddl_deadline(card["item"])
            status_label = STATUS_META.get(card["display_status"], STATUS_META["pending"])[0]
            source_title = str(card["record"].get("title") or "未命名通知")
            base = f"{title}\n截止：{deadline}\n状态：{status_label}\n来源：{source_title}"
            count = counts.get(base, 0) + 1
            counts[base] = count
            label = base if count == 1 else f"{base}\n记录：{card['record']['id']}:{card['ddl_id']}"
            labels.append(label)
            label_to_card[label] = card

        st.markdown('<div class="task-list-title">拖动下方任务卡片调整优先级</div><div class="task-list-hint">卡片本身就是拖拽项。越靠上越先做，拖动后今日主攻和操作顺序会同步变化。</div>', unsafe_allow_html=True)
        sorted_labels = sort_items(
            labels,
            direction="vertical",
            key="workspace_ddl_order_drag",
            custom_style="""
            .sortable-component { border:0; padding:0; background:transparent; }
            .sortable-container, .sortable-container-body { background:transparent; padding:0; }
            .sortable-item { background:linear-gradient(135deg,#0f172a,#1e3a8a); border:1px solid rgba(147,197,253,.35); border-radius:24px; padding:18px 20px; margin:12px 0; min-height:176px; height:176px; display:block; font-weight:800; color:#fff; cursor:grab; box-shadow:0 14px 30px rgba(15,23,42,.18); white-space:pre-line; overflow:hidden; line-height:1.55; touch-action:none; user-select:none; }
            .sortable-item.active:not(.dragging) { opacity:.30; }
            .sortable-item.dragging { cursor:grabbing; opacity:1; box-shadow:0 18px 38px rgba(15,23,42,.2); }
            """,
        )
        st.session_state.workspace_drag_order = [f"{label_to_card[label]['record']['id']}::{label_to_card[label]['ddl_id']}" for label in sorted_labels if label in label_to_card]
        if sorted_labels != labels:
            records_to_save: dict[str, dict] = {}
            for card_order, label in enumerate(sorted_labels):
                card = label_to_card.get(label)
                if not card:
                    continue
                for task_index, task in enumerate(card["item"].get("tasks") or []):
                    if not isinstance(task, dict):
                        continue
                    task["manual_priority"] = True
                    task["manual_order"] = card_order * 100 + task_index
                records_to_save[card["record"]["id"]] = card["record"]
            for record in records_to_save.values():
                save_notice(record.get("parsed") or {}, raw_text=record.get("raw_text"), record_id=record["id"])
            ordered_cards = [label_to_card[x] for x in sorted_labels if x in label_to_card]
            order_index = {f"{card['record']['id']}::{card['ddl_id']}": i for i, card in enumerate(ordered_cards)}
            cards.sort(key=lambda card: order_index.get(f"{card['record']['id']}::{card['ddl_id']}", 9999))
            for card in cards:
                if card.get("display_status") == "primary":
                    card["display_status"] = card["status"]
            pending_cards = [card for card in cards if card["status"] == "pending" and not card["expired"]]
            if pending_cards:
                pending_cards[0]["display_status"] = "primary"
            st.caption("顺序已更新：卡片顺序和今日主攻都已变化。")

    if st.button("生成全工作台今日计划", type="primary", use_container_width=True, key="workspace_aggregate"):
        notifications = []
        for record in records:
            parsed = _active_parsed_for_ddl(record, now)
            if parsed is None:
                continue
            parsed["notification_id"] = record["id"]
            source = parsed.get("source") if isinstance(parsed.get("source"), dict) else {}
            source.setdefault("title", record["title"])
            source.setdefault("captured_at", record["created_at"])
            parsed["source"] = source
            notifications.append(parsed)
        if not notifications:
            st.warning("工作台里没有未完成且未过期的 DDL，暂时没有需要聚合的任务。")
        else:
            try:
                aggregated = aggregate_notifications(notifications)
                aggregated["deadline_iso"] = aggregated["deadline"]["normalized"]
                aggregated["schedule_ready"] = True
                aggregated["raw_text"] = "；".join(
                    record["raw_text"] for record in records
                    if _active_parsed_for_ddl(record, now)
                )
                st.session_state.workspace_aggregated = aggregated
                st.session_state.workspace_plan = build_plan(
                    aggregated,
                    available_minutes=int(st.session_state.get("available_minutes", 120)),
                    days=7,
                )
                st.session_state.workspace_plan_stale = False
                st.toast("已生成跨通知工作台计划")
                st.rerun()
            except Exception as exc:  # noqa: BLE001 - 错误需要显示给用户
                st.error(f"跨通知聚合失败：{exc}")

    workspace_plan = st.session_state.get("workspace_plan")
    workspace_aggregated = st.session_state.get("workspace_aggregated")
    if workspace_plan and workspace_aggregated:
        st.markdown("#### 全工作台今日计划")
        if st.session_state.get("workspace_plan_stale"):
            st.warning("工作台状态已变化，当前计划已过期。请点击上方“生成全工作台今日计划”重新生成。")
        m1, m2, m3 = st.columns(3)
        metric_prefix = "旧计划 · " if st.session_state.get("workspace_plan_stale") else ""
        m1, m2 = st.columns(2)
        m1.metric(f"{metric_prefix}汇总 DDL", len(workspace_aggregated.get("ddl_items", [])))
        m2.metric(f"{metric_prefix}总任务时长", f"{workspace_plan.get('required_minutes', 0)} 分钟")
        st.markdown(f"**{metric_prefix}今日主攻：{html.escape(str(workspace_plan.get('today_deliverable', '待确认')))}**")
        if workspace_plan.get("plan_days"):
            for day in workspace_plan["plan_days"][:2]:
                titles = "、".join(str(task.get("title", "任务")) for task in day.get("tasks", []))
                st.markdown(f"- **{day.get('day', '今天')}**：{titles}")
        st.caption("这是跨通知聚合结果；载入单条通知可继续编辑，下一步可继续细化每日顺序。")
        st.info(_next_step_message(cards, st.session_state.get("workspace_plan_stale", False)))

    for card in cards:
        record = card["record"]
        item = card["item"]
        ddl_id = card["ddl_id"]
        status = card["status"]
        display_status = card["display_status"]
        status_label, status_class = STATUS_META.get(display_status, STATUS_META["pending"])
        underlying_label = STATUS_META.get(status, STATUS_META["pending"])[0]
        status_note = (
            f'<span class="tag">DDL状态：{html.escape(underlying_label)}</span>'
            if display_status == "primary" else ""
        )
        suffix = record["id"] if card["card_count"] == 1 else f"{record['id']}_{ddl_id}"
        reward_points = _ddl_reward_points(record, ddl_id)
        st.markdown(f"**{html.escape(str(item.get('title') or '未命名 DDL'))}** · {html.escape(status_label)} · 截止 {html.escape(_format_ddl_deadline(item))} · 完成 +{reward_points} 分")
        current_target = str(item.get("target_level") or "保底")
        target_level = st.selectbox(
            "目标强度",
            ["保底", "进阶", "挑战"],
            index=["保底", "进阶", "挑战"].index(current_target) if current_target in ["保底", "进阶", "挑战"] else 0,
            key=f"workspace_level_{suffix}",
            help="保底 +20、进阶 +40、挑战 +60。",
        )
        if target_level != current_target:
            item["target_level"] = target_level
            save_notice(record.get("parsed") or {}, raw_text=record.get("raw_text"), record_id=record["id"])
        load_col, start_col, complete_col, stuck_col, delete_col = st.columns([1.2, 1.0, 1.0, 1.0, 0.8])
        with load_col:
            st.button(
                "载入编辑",
                key=f"workspace_load_{suffix}",
                use_container_width=True,
                on_click=load_record_for_edit,
                args=(record["id"],),
            )
        with start_col:
            if status == "active":
                if st.button("继续", key=f"workspace_continue_{suffix}", use_container_width=True):
                    _apply_ddl_status(record, ddl_id, "active", card["has_ddl_row"])
                    st.rerun()
            elif status not in {"done", "stuck"}:
                if st.button("开始", key=f"workspace_start_{suffix}", use_container_width=True):
                    _apply_ddl_status(record, ddl_id, "active", card["has_ddl_row"])
                    st.rerun()
        with complete_col:
            if status != "done":
                if st.button("标记完成", key=f"workspace_status_{suffix}", use_container_width=True):
                    _apply_ddl_status(record, ddl_id, "done", card["has_ddl_row"])
                    st.rerun()
            else:
                if st.button("重新打开", key=f"workspace_status_{suffix}", use_container_width=True):
                    _apply_ddl_status(record, ddl_id, "reopened", card["has_ddl_row"])
                    st.rerun()
        with stuck_col:
            if status == "stuck":
                if st.button("继续", key=f"workspace_stuck_{suffix}", use_container_width=True):
                    _apply_ddl_status(record, ddl_id, "active", card["has_ddl_row"])
                    st.rerun()
            elif status in {"active", "primary"}:
                if st.button("我卡住了", key=f"workspace_stuck_{suffix}", use_container_width=True):
                    _apply_ddl_status(record, ddl_id, "stuck", card["has_ddl_row"])
                    st.rerun()
        with delete_col:
            if st.button("删除任务", key=f"workspace_delete_task_{suffix}", use_container_width=True):
                st.session_state.workspace_delete_ddl_confirm = f"{record['id']}::{ddl_id}"
                st.rerun()

        confirm_key = f"{record['id']}::{ddl_id}"
        if st.session_state.get("workspace_delete_ddl_confirm") == confirm_key:
            st.warning(f"确认删除任务“{item.get('title') or '未命名任务'}”？同一通知里的其他任务不会删除。")
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button("确认删除任务", key=f"workspace_confirm_delete_task_{suffix}", use_container_width=True):
                    delete_ddl_task(record["id"], ddl_id)
                    st.rerun()
            with cancel_col:
                if st.button("取消", key=f"workspace_cancel_delete_task_{suffix}", use_container_width=True):
                    st.session_state.workspace_delete_ddl_confirm = None
                    st.rerun()

    st.info(_next_step_message(cards, st.session_state.get("workspace_plan_stale", False)))


def reset_for_new_notice() -> None:
    clear_editor_keys()
    st.session_state.parsed = None
    st.session_state.plan = None
    st.session_state.started = False
    st.session_state.completed = False
    st.session_state.stuck = False
    st.session_state.replan = None
    st.session_state.remaining_minutes = 15
    st.session_state.current_record_id = None
    st.session_state.workspace_plan = None
    st.session_state.workspace_aggregated = None



st.markdown(
    """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display:none !important;}
[data-testid="stToolbar"], #MainMenu, footer {visibility:hidden;}
.block-container {max-width: 760px; padding-top: .7rem !important;}
.simple-hero {margin-bottom: .55rem !important; padding: 1rem 1.1rem !important; border-radius: 20px !important;}
.simple-hero h1 {font-size: clamp(1.55rem, 7vw, 2.5rem) !important; line-height: 1.08 !important; margin-top: .5rem !important;}
.simple-hero p {max-width: 680px; font-size: .92rem !important; line-height: 1.55 !important; margin-bottom: 0 !important;}
.simple-steps {display:flex; gap:.4rem; margin:.5rem 0 .75rem;}
.simple-step {flex:1; padding:.5rem .35rem; border-radius:12px; background:#eef2f7; color:#64748b; font-size:.76rem; font-weight:800; text-align:center; border:1px solid #e2e8f0;}
.simple-step.active {background:#2563eb; color:white; border-color:#2563eb;}
.simple-step.done {background:#dcfce7; color:#166534; border-color:#bbf7d0;}
.simple-kicker {color:#2563eb; font-weight:900; letter-spacing:.08em; font-size:.78rem; margin-bottom:.25rem;}
.simple-question {font-size:1.35rem; font-weight:900; color:#0f172a; margin:.15rem 0 .45rem;}
.simple-note {color:#64748b; font-size:.88rem; margin-bottom:.55rem;}
.simple-result {background:#fff; border:1px solid #dbeafe; border-radius:18px; padding:1rem 1.1rem; margin:.65rem 0;}
.simple-result b {color:#0f172a;}
.simple-result small {color:#64748b; display:block; margin-top:.25rem;}
.simple-focus {background:linear-gradient(135deg,#0f172a,#1e3a8a); color:white; border-radius:24px; padding:1.35rem; margin:.7rem 0 1rem;}
.simple-focus h2 {color:white !important; font-size:clamp(1.55rem, 6vw, 2.4rem); line-height:1.2; margin:.45rem 0;}
.simple-focus p {color:#dbeafe; margin:.25rem 0;}
.simple-focus .badge {background:rgba(255,255,255,.14); color:#bfdbfe;}
.task-list-title {font-size:1.25rem; font-weight:900; color:#0f172a; margin:.35rem 0 .15rem;}
.task-list-hint {font-size:.85rem; color:#64748b; margin-bottom:.4rem;}
.reward-card {background:linear-gradient(135deg,#fff7ed,#eff6ff); border:1px solid #fde68a; border-radius:18px; padding:1rem 1.1rem; margin:.7rem 0 1rem;}
.reward-title {font-size:.78rem; letter-spacing:.08em; color:#b45309; font-weight:900;}
.reward-points {font-size:2rem; line-height:1.05; font-weight:900; color:#0f172a; margin:.3rem 0;}
.reward-copy {font-size:.9rem; color:#475569; margin:.15rem 0;}
.reward-pill {display:inline-block; padding:.28rem .6rem; border-radius:999px; background:#fff; border:1px solid #fcd34d; color:#92400e; font-size:.78rem; font-weight:800; margin-top:.45rem;}
.reward-stat-row {display:flex; gap:.5rem; margin:.55rem 0 .25rem;}
.reward-stat {flex:1; background:rgba(255,255,255,.8); border-radius:12px; padding:.55rem .6rem; text-align:center;}
.reward-stat b {display:block; font-size:1.15rem; color:#0f172a;}
.reward-stat span {font-size:.72rem; color:#64748b;}
@media (max-width: 520px) {
  .block-container {padding-left:1rem; padding-right:1rem;}
  .simple-steps {gap:.3rem;}
  .simple-step {padding:.55rem .3rem; font-size:.72rem;}
}
</style>
""",
    unsafe_allow_html=True,
)

provider_defaults = environment_defaults()
provider_mode = st.session_state.get("provider_mode", "mock")


def guided_step() -> int:
    if st.session_state.get("parsed") and st.session_state.get("plan"):
        return 3
    if st.session_state.get("parsed"):
        return 2
    return 1


def grant_reward(points: int, key: str, *, count_completion: bool = True, reason: str = "任务完成", celebrate: bool = False) -> int:
    claimed = set(st.session_state.get("reward_claimed_keys", []))
    if key in claimed:
        return 0
    claimed.add(key)
    st.session_state.reward_claimed_keys = sorted(claimed)
    st.session_state.reward_xp = int(st.session_state.get("reward_xp", 0)) + int(points)
    st.session_state.last_reward_points = int(points)
    if count_completion:
        st.session_state.reward_completed_count = int(st.session_state.get("reward_completed_count", 0)) + 1
        st.session_state.reward_streak = int(st.session_state.get("reward_streak", 0)) + 1
    st.session_state.reward_notice = f"{reason}，+{int(points)} 分已到账！"
    st.toast(st.session_state.reward_notice)
    if celebrate:
        st.balloons()
    return int(points)


def reward_badge(points: int) -> tuple[str, str]:
    if points >= 160:
        return "急救大师", "你已经把“先做一步”变成了稳定习惯。"
    if points >= 80:
        return "反拖延选手", "不是靠硬撑，而是一次次把任务收小、做完。"
    if points >= 20:
        return "今日启动者", "只要开始，今天就已经和昨天不一样。"
    return "刚刚起步", "完成第一块，就会点亮今天的第一个奖励。"


def render_reward_summary(compact: bool = False) -> None:
    points = int(st.session_state.get("reward_xp", 0))
    completed = int(st.session_state.get("reward_completed_count", 0))
    streak = int(st.session_state.get("reward_streak", 0))
    badge, copy = reward_badge(points)
    card = (
        '<div class="reward-card">'
        '<div class="reward-title">今日正反馈</div>'
        f'<div class="reward-points">{points} 分</div>'
        f'<div class="reward-copy">{html.escape(copy)}</div>'
        '<div class="reward-stat-row">'
        f'<div class="reward-stat"><b>{completed}</b><span>完成任务</span></div>'
        f'<div class="reward-stat"><b>{streak}</b><span>连续完成</span></div>'
        f'<div class="reward-stat"><b>{html.escape(badge)}</b><span>当前徽章</span></div>'
        '</div></div>'
    )
    st.markdown(card, unsafe_allow_html=True)
    goals = [(40, "今日启动者"), (80, "反拖延选手"), (160, "急救大师")]
    next_goal = next(((target, label) for target, label in goals if points < target), None)
    if next_goal:
        target, label = next_goal
        st.progress(min(points / target, 1.0), text=f"距离「{label}」还差 {target - points} 分")
    else:
        st.caption("最高徽章已点亮。继续完成，记录不会清零。")


def render_steps(active: int) -> None:
    labels = [("1", "粘贴通知"), ("2", "生成计划"), ("3", "今天做")]
    parts = []
    for number, label in labels:
        idx = int(number)
        cls = "active" if idx == active else ("done" if idx < active else "")
        parts.append(f'<div class="simple-step {cls}">{number} · {label}</div>')
    st.markdown('<div class="simple-steps">' + "".join(parts) + "</div>", unsafe_allow_html=True)


def reset_guided() -> None:
    clear_editor_keys()
    st.session_state.parsed = None
    st.session_state.plan = None
    st.session_state.started = False
    st.session_state.completed = False
    st.session_state.stuck = False
    st.session_state.replan = None
    st.session_state.remaining_minutes = 15
    st.session_state.current_record_id = None
    st.session_state.workspace_plan = None
    st.session_state.workspace_aggregated = None
    st.session_state.notice_text = ""


def save_parsed_notice(parsed: dict, raw_text: str, *, reset_statuses: bool = False) -> str:
    normalized_text = str(raw_text).strip()
    existing = next(
        (
            item for item in list_notices()
            if str(item.get("raw_text") or "").strip() == normalized_text
            or (
                str(item.get("title") or "").strip() == str(parsed.get("title") or "").strip()
                and str(item.get("parsed", {}).get("deadline_iso") or "")
                == str(parsed.get("deadline_iso") or "")
            )
        ),
        None,
    )
    saved = save_notice(
        parsed,
        raw_text=raw_text,
        record_id=existing["id"] if existing else st.session_state.get("current_record_id"),
    )
    st.session_state.current_record_id = saved["id"]
    if reset_statuses:
        record_id = saved["id"]
        update_status(record_id, "pending")
        for item in parsed.get("ddl_items") or []:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                update_ddl_status(record_id, str(item["id"]), "pending")
        st.session_state.reward_claimed_keys = [
            key for key in st.session_state.get("reward_claimed_keys", [])
            if record_id not in str(key)
        ]
        st.session_state.completed = False
        st.session_state.started = False
        st.session_state.stuck = False
        st.session_state.replan = None
    return saved["id"]


def run_parse(raw_text: str, *, reset_statuses: bool = False) -> None:
    text = str(raw_text or "").strip()
    if not text:
        st.warning("先粘贴一条作业通知。")
        return
    with st.spinner("正在拆出截止任务和今天的第一步…"):
        parsed, provider_label, fallback_reason = parse_notice(
            text,
            mode=st.session_state.get("provider_mode", "mock"),
            base_url=st.session_state.get("llm_base_url", provider_defaults["base_url"]),
            api_key=st.session_state.get("llm_api_key", provider_defaults["api_key"]),
            model=st.session_state.get("llm_model", provider_defaults["model"]),
        )
        save_parsed_notice(parsed, text, reset_statuses=reset_statuses)
    st.session_state.parsed = parsed
    st.session_state.plan = None
    st.session_state.started = False
    st.session_state.completed = False
    st.session_state.stuck = False
    st.session_state.replan = None
    st.session_state.provider_label = provider_label
    st.session_state.fallback_reason = fallback_reason
    st.rerun()


active_step = guided_step()
planned_section = st.session_state.get("guided_section", "急救流程")
page_signature = f"{planned_section}:{active_step if planned_section == '急救流程' else 'tasks'}"
if st.session_state.get("last_page_signature") != page_signature:
    st.session_state.last_page_signature = page_signature
    st.markdown(
        """
<div class="ddl-transition-overlay" aria-hidden="true">
  <div class="ddl-light ddl-light-a"></div>
  <div class="ddl-light ddl-light-b"></div>
  <div class="ddl-sheen"></div>
  <div class="ddl-transition-panel">
    <div class="ddl-emblem">🚑</div>
    <div class="ddl-brand">DDL 急救站</div>
    <div class="ddl-sub">把今天，收成一个动作</div>
    <div class="ddl-progress"><span></span></div>
  </div>
</div>
<style>
@keyframes ddlVeil {
  0% { opacity: 0; }
  12% { opacity: 1; }
  72% { opacity: 1; }
  100% { opacity: 0; }
}
@keyframes ddlPanelIn {
  0% { opacity: 0; transform: translate(-50%, calc(-50% + 18px)) scale(.92); }
  20% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
  72% { opacity: 1; transform: translate(-50%, calc(-50% - 2px)) scale(1); }
  100% { opacity: 0; transform: translate(-50%, calc(-50% - 14px)) scale(.98); }
}
@keyframes ddlLightA {
  0% { transform: translate3d(-18%, -12%, 0) scale(.82); }
  100% { transform: translate3d(16%, 12%, 0) scale(1.18); }
}
@keyframes ddlLightB {
  0% { transform: translate3d(14%, 10%, 0) scale(.88); }
  100% { transform: translate3d(-16%, -10%, 0) scale(1.22); }
}
@keyframes ddlSheen {
  0% { transform: translateX(-170%) skewX(-18deg); opacity: 0; }
  24% { opacity: .9; }
  100% { transform: translateX(240%) skewX(-18deg); opacity: 0; }
}
@keyframes ddlEmblem {
  0% { opacity: 0; transform: scale(.55) rotate(-12deg); }
  30% { opacity: 1; transform: scale(1.08) rotate(2deg); }
  58% { transform: scale(1) rotate(0); }
  100% { transform: scale(1) rotate(0); }
}
@keyframes ddlProgressFill {
  0% { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}
.ddl-transition-overlay {
  position: fixed; inset: 0; z-index: 9998; pointer-events: none; overflow: hidden;
  background: linear-gradient(135deg, rgba(219,234,254,.92), rgba(248,250,252,.88) 46%, rgba(224,242,254,.9));
  will-change: opacity; animation: ddlVeil .78s cubic-bezier(.18,.78,.2,1) both;
}
.ddl-light { position: absolute; width: 76vw; height: 76vw; border-radius: 50%; opacity: .55; will-change: transform; }
.ddl-light-a { left: -24vw; top: -31vw; background: radial-gradient(circle, rgba(59,130,246,.48), rgba(59,130,246,0) 68%); animation: ddlLightA .9s ease-out both; }
.ddl-light-b { right: -27vw; bottom: -34vw; background: radial-gradient(circle, rgba(14,165,233,.34), rgba(14,165,233,0) 70%); animation: ddlLightB .9s ease-out both; }
.ddl-sheen { position: absolute; top: -30%; bottom: -30%; left: 0; width: 24vw; background: linear-gradient(90deg, transparent, rgba(255,255,255,.75), transparent); will-change: transform, opacity; animation: ddlSheen .78s ease-out both; }
.ddl-transition-panel {
  position: absolute; top: 50%; left: 50%; z-index: 1; width: min(78vw, 310px); padding: 1.15rem 1.2rem 1rem; text-align: center;
  border-radius: 28px; color: #fff; background: linear-gradient(145deg, rgba(15,23,42,.96), rgba(30,64,175,.94));
  border: 1px solid rgba(191,219,254,.45); box-shadow: 0 26px 70px rgba(30,64,175,.28), inset 0 1px 0 rgba(255,255,255,.16);
  will-change: opacity, transform; animation: ddlPanelIn .78s cubic-bezier(.18,.78,.2,1) both;
}
.ddl-emblem { width: 54px; height: 54px; margin: 0 auto .6rem; display: grid; place-items: center; border-radius: 18px; font-size: 1.55rem; background: linear-gradient(145deg,#60a5fa,#2563eb); box-shadow: 0 10px 26px rgba(37,99,235,.42); animation: ddlEmblem .78s cubic-bezier(.18,.78,.2,1) both; }
.ddl-brand { font-size: 1.1rem; font-weight: 900; letter-spacing: .08em; }
.ddl-sub { margin-top: .35rem; color: #bfdbfe; font-size: .76rem; font-weight: 700; letter-spacing: .12em; }
.ddl-progress { height: 3px; margin:.85rem auto .1rem; width: 72%; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.18); }
.ddl-progress span { display:block; height:100%; width:100%; transform-origin:left; border-radius:999px; background:linear-gradient(90deg,#93c5fd,#fff,#67e8f9); animation:ddlProgressFill .7s cubic-bezier(.2,.8,.2,1) both; }
@media (prefers-reduced-motion: reduce) {
  .ddl-transition-overlay, .ddl-transition-panel, .ddl-emblem, .ddl-light, .ddl-sheen, .ddl-progress span { animation: none !important; opacity: 0 !important; }
}
</style>
""",
        unsafe_allow_html=True,
    )

st.markdown(
    """
<div class="hero simple-hero">
  <span class="badge">3 步完成今天的作业</span>
  <h1>别想全部，先完成今天这一步。</h1>
  <p>把钉钉或群里的作业通知粘进来，自动拆成截止任务，再给你一个今天能交付的结果。</p>
</div>
""",
    unsafe_allow_html=True,
)
if "guided_section" not in st.session_state:
    st.session_state.guided_section = "急救流程"
section = st.segmented_control(
    "页面",
    ["急救流程", "我的任务"],
    key="guided_section",
    label_visibility="collapsed",
    width="stretch",
)
def switch_to_my_tasks() -> None:
    st.session_state.guided_section = "我的任务"


if section == "我的任务":
    st.markdown('<div class="simple-kicker">我的任务</div><div class="simple-question">先做什么，由你决定</div><div class="simple-note">保存过的 DDL 都在下面；拖动排序后，今日主攻和计划顺序会一起更新。</div>', unsafe_allow_html=True)
    render_reward_summary(compact=True)
    if st.session_state.get("reward_notice"):
        st.success(st.session_state.reward_notice)
    render_workspace(draggable=True)
    st.stop()

render_steps(active_step)

if active_step == 1:
    st.markdown('<div class="simple-kicker">第 1 步</div><div class="simple-question">粘贴一条作业通知</div><div class="simple-note">不用整理格式，照原样复制即可。</div>', unsafe_allow_html=True)
    st.text_area(
        "作业通知",
        key="notice_text",
        height=135,
        label_visibility="collapsed",
        placeholder="例如：数学分析第 3 次作业，完成习题 1-5，11月25日23:59前提交。",
    )

    def queue_demo() -> None:
        demo = next((case for case in SAMPLE_CASES if case["id"] == "multi_ddl"), SAMPLE_CASES[0])
        st.session_state.notice_text = demo["text"]
        st.session_state["available_minutes"] = demo.get("demo_minutes", 120)
        st.session_state.guided_demo_requested = True

    st.button(
        "没有通知？点这里用示例体验",
        use_container_width=True,
        key="guided_demo",
        on_click=queue_demo,
    )

    if st.button("开始急救", type="primary", use_container_width=True, key="guided_parse"):
        run_parse(st.session_state.get("notice_text", ""), reset_statuses=True)

    if st.session_state.pop("guided_demo_requested", False):
        run_parse(st.session_state.get("notice_text", ""), reset_statuses=True)

    with st.expander("高级设置：真实模型（通常不用改）"):
        st.selectbox(
            "解析方式",
            ["mock", "real"],
            format_func=lambda x: "模拟解析（推荐演示）" if x == "mock" else "真实模型",
            key="provider_mode",
        )
        if st.session_state.get("provider_mode") == "real":
            st.text_input("接口地址", value=provider_defaults["base_url"], key="llm_base_url")
            st.text_input("模型名称", value=provider_defaults["model"], key="llm_model")
            st.text_input("API Key", value=provider_defaults["api_key"], type="password", key="llm_api_key")
            st.caption("调用失败会自动回退模拟解析，不会卡住流程。")

elif active_step == 2:
    parsed = st.session_state.parsed
    items = parsed.get("ddl_items")
    if not isinstance(items, list) or not items:
        items = [{
            "id": "DDL1",
            "title": parsed.get("title") or "作业任务",
            "deadline_iso": parsed.get("deadline_iso"),
            "deadline": {"normalized": parsed.get("deadline_iso")} if parsed.get("deadline_iso") else None,
        }]

    st.markdown('<div class="simple-kicker">第 2 步</div><div class="simple-question">这次要完成什么？</div>', unsafe_allow_html=True)
    st.caption(f"识别到 {len(items)} 个截止任务。先确认，再生成今天能做的计划。")
    for item in items:
        deadline_iso = item.get("deadline_iso") or (item.get("deadline") or {}).get("normalized")
        try:
            deadline_label = datetime.fromisoformat(str(deadline_iso)).strftime("%m月%d日 %H:%M") if deadline_iso else "待确认"
        except ValueError:
            deadline_label = str(deadline_iso)
        tasks = item.get("tasks") or []
        task_summary = "；".join(
            f'{task.get("title") or "任务"}（{ {"high": "高", "normal": "普通", "low": "低"}.get(str(task.get("priority") or "normal"), "普通") }）'
            for task in tasks if isinstance(task, dict)
        ) or "尚未拆出任务"
        st.markdown(
            f'<div class="simple-result"><b>{html.escape(str(item.get("title") or "作业任务"))}</b><small>截止：{html.escape(deadline_label)}</small><small>任务：{html.escape(task_summary)}</small></div>',
            unsafe_allow_html=True,
        )

    if parsed.get("risks"):
        st.warning("有些信息需要人工确认：" + "；".join(str(risk.get("message") or "") for risk in parsed["risks"] if isinstance(risk, dict)))

    st.markdown('<div class="task-list-title">任务列表</div><div class="task-list-hint">按你的真实优先级排列所有任务。按住卡片上下拖动，越靠上越先做。</div>', unsafe_allow_html=True)
    task_labels: list[str] = []
    task_by_label: dict[str, tuple[dict, dict]] = {}
    label_counts: dict[str, int] = {}
    for ddl_index, item in enumerate(items):
        ddl_title = str(item.get("title") or "作业任务")
        ddl_key = str(item.get("id") or f"DDL{ddl_index + 1}")
        for task_index, task in enumerate(item.get("tasks") or []):
            if not isinstance(task, dict):
                continue
            task_title = str(task.get("title") or "任务")
            task_key = str(task.get("id") or f"T{task_index + 1}")
            base_label = f"{task_title} ｜ {ddl_title}"
            count = label_counts.get(base_label, 0) + 1
            label_counts[base_label] = count
            label = base_label if count == 1 else f"{base_label} ｜ {ddl_key}:{task_key}"
            task_labels.append(label)
            task_by_label[label] = (item, task)

    if task_labels:
        sorted_labels = sort_items(
            task_labels,
            direction="vertical",
            key="guided_task_order_drag",
            custom_style="""
            .sortable-component { border: 0; padding: 0; background: transparent; }
            .sortable-container { background: transparent; }
            .sortable-container-body { background: transparent; padding: 0; }
            .sortable-container-body { min-height: 56px; }
            .sortable-item { background:#fff; border:1px solid #dbe4f0; border-radius:14px; padding:0 16px; margin:8px 0; min-height:56px; height:56px; display:flex; align-items:center; font-weight:800; color:#1e293b; cursor:grab; box-shadow:0 3px 12px rgba(15,23,42,.05); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; line-height:1.2; touch-action:none; user-select:none; }
            .sortable-item:hover { border-color:#93c5fd; background:#f8fbff; }
            .sortable-item.active:not(.dragging) { opacity:.30; }
            .sortable-item.dragging { cursor:grabbing; opacity:1; box-shadow:0 14px 32px rgba(15,23,42,.18); }
            """,
        )
        st.session_state.guided_drag_order = sorted_labels
        if sorted_labels != task_labels:
            for order, label in enumerate(sorted_labels):
                pair = task_by_label.get(label)
                if not pair:
                    continue
                _, drag_task = pair
                drag_task["manual_priority"] = True
                drag_task["manual_order"] = order
            st.session_state.parsed = parsed
            st.caption("顺序已更新，生成计划时会按这个顺序排期。")
        else:
            st.caption("按住卡片上下拖动。拖动顺序会直接进入排期。")
    else:
        st.info("还没有拆出任务，请展开下方“修改识别结果”补充任务。")

    with st.expander("修改识别结果：通知、截止时间、任务、优先级", expanded=False):
        with st.form("guided_edit_form"):
            edited_items = deepcopy(items)
            for ddl_index, edit_item in enumerate(edited_items):
                st.markdown(f"**截止任务 {ddl_index + 1}**")
                edit_item["title"] = st.text_input(
                    "任务名称",
                    value=str(edit_item.get("title") or "作业任务"),
                    key=f"guided_ddl_title_{ddl_index}",
                )
                current_iso = edit_item.get("deadline_iso") or (edit_item.get("deadline") or {}).get("normalized")
                current_deadline = ""
                if current_iso:
                    try:
                        current_deadline = datetime.fromisoformat(str(current_iso)).strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        current_deadline = str(current_iso)
                edit_item["_edit_deadline"] = st.text_input(
                    "截止时间（YYYY-MM-DD HH:MM）",
                    value=current_deadline,
                    key=f"guided_ddl_deadline_{ddl_index}",
                )
                edit_tasks = edit_item.get("tasks") or []
                for task_index, edit_task in enumerate(edit_tasks):
                    if not isinstance(edit_task, dict):
                        continue
                    st.caption(f"任务 {ddl_index + 1}.{task_index + 1}")
                    edit_task["title"] = st.text_input(
                        "任务内容",
                        value=str(edit_task.get("title") or "任务"),
                        key=f"guided_task_title_{ddl_index}_{task_index}",
                    )
                    edit_task["minutes"] = int(st.number_input(
                        "预计分钟",
                        min_value=5,
                        max_value=240,
                        value=int(edit_task.get("minutes") or edit_task.get("estimate_min") or 30),
                        step=5,
                        key=f"guided_task_minutes_{ddl_index}_{task_index}",
                    ))
                    edit_task["priority"] = st.selectbox(
                        "优先级",
                        ["high", "normal", "low"],
                        index=["high", "normal", "low"].index(str(edit_task.get("priority") or "normal"))
                        if str(edit_task.get("priority") or "normal") in ["high", "normal", "low"] else 1,
                        format_func=lambda value: {"high": "高", "normal": "普通", "low": "低"}[value],
                        key=f"guided_task_priority_{ddl_index}_{task_index}",
                    )
                    edit_task["manual_priority"] = True
            apply_edits = st.form_submit_button("保存修改", type="primary", use_container_width=True)

        if apply_edits:
            valid = True
            valid_items = []
            for edit_item in edited_items:
                deadline_text = str(edit_item.pop("_edit_deadline", "") or "").strip()
                iso = deadline_to_iso(deadline_text)
                if not iso:
                    st.error(f"“{edit_item.get('title') or '任务'}”的截止时间格式不对，请用 YYYY-MM-DD HH:MM。")
                    valid = False
                    continue
                edit_item["deadline_iso"] = iso
                edit_item["deadline"] = {"normalized": iso, "raw": deadline_text, "confidence": 1.0, "source_span": deadline_text}
                for edit_task in edit_item.get("tasks") or []:
                    if not isinstance(edit_task, dict):
                        continue
                    minutes = int(edit_task.get("minutes") or 30)
                    edit_task["estimate_min"] = minutes
                    levels = edit_task.setdefault("levels", {})
                    minimum = levels.setdefault("minimum", {"label": "保底", "deliverable": edit_task.get("title") or "任务", "minutes": minutes, "done_definition": f"{edit_task.get('title') or '任务'}已有可见成果。"})
                    minimum["deliverable"] = edit_task.get("title") or minimum.get("deliverable") or "任务"
                    minimum["minutes"] = minutes
                    for level_name in ("standard", "stretch"):
                        level = levels.get(level_name)
                        if isinstance(level, dict):
                            level["minutes"] = max(int(level.get("minutes") or minutes), minutes)
                valid_items.append(edit_item)
            if valid and len(valid_items) == len(edited_items):
                parsed["ddl_items"] = valid_items
                parsed["deliverables"] = [str(item.get("title") or "任务") for item in valid_items]
                deadlines = [item.get("deadline_iso") for item in valid_items if item.get("deadline_iso")]
                parsed["deadline_iso"] = min(deadlines) if deadlines else None
                if parsed["deadline_iso"]:
                    parsed["deadline"] = datetime.fromisoformat(parsed["deadline_iso"]).strftime("%Y-%m-%d %H:%M")
                else:
                    parsed["deadline"] = "待确认"
                parsed["schedule_ready"] = bool(parsed["deadline_iso"])
                st.session_state.parsed = parsed
                save_parsed_notice(parsed, st.session_state.get("notice_text", parsed.get("raw_text", "")))
                st.toast("识别结果已更新")
                st.rerun()

    with st.expander("修改原文并重新识别"):
        edited_raw = st.text_area(
            "通知原文",
            value=st.session_state.get("notice_text", parsed.get("raw_text", "")),
            height=150,
            key="guided_raw_edit",
        )
        def queue_raw_reparse() -> None:
            st.session_state.notice_text = st.session_state.get("guided_raw_edit", "")
            st.session_state.guided_raw_requested = True

        st.button("重新解析原文", use_container_width=True, on_click=queue_raw_reparse)
        if st.session_state.pop("guided_raw_requested", False):
            run_parse(st.session_state.get("notice_text", ""), reset_statuses=False)

    st.markdown('<div class="simple-question" style="font-size:1.2rem;margin-top:1rem;">你每天大概能投入多久？</div>', unsafe_allow_html=True)
    available_minutes = st.slider(
        "每天可用时间",
        min_value=30,
        max_value=240,
        value=int(st.session_state.get("available_minutes", 90)),
        step=15,
        label_visibility="collapsed",
    )
    st.session_state.available_minutes = available_minutes

    col_back, col_plan = st.columns([1, 2])
    with col_back:
        if st.button("重新粘贴", use_container_width=True):
            st.session_state.parsed = None
            st.session_state.plan = None
            st.rerun()
    with col_plan:
        if st.button("生成今日行动计划", type="primary", use_container_width=True):
            drag_order = st.session_state.get("guided_drag_order") or []
            for order, label in enumerate(drag_order):
                pair = task_by_label.get(label)
                if not pair:
                    continue
                _, drag_task = pair
                drag_task["manual_priority"] = True
                drag_task["manual_order"] = order
            st.session_state.parsed = parsed
            save_parsed_notice(parsed, st.session_state.get("notice_text", parsed.get("raw_text", "")))
            st.session_state.plan = build_plan(parsed, available_minutes=available_minutes, days=7)
            st.session_state.started = False
            st.session_state.completed = False
            st.session_state.stuck = False
            st.session_state.replan = None
            st.session_state.start_bonus_awarded = False
            st.session_state.remaining_minutes = max(5, min(240, int(st.session_state.plan.get("today_minutes", 30)) // 2))
            st.rerun()

    with st.expander("识别不对？查看原文和风险"):
        st.text_area("原文", value=st.session_state.get("notice_text", ""), height=150, disabled=True)
        if st.session_state.get("fallback_reason"):
            st.caption(str(st.session_state.fallback_reason))

else:
    parsed = st.session_state.parsed
    plan = normalize_plan(st.session_state.plan)
    st.markdown('<div class="simple-kicker">第 3 步</div><div class="simple-question">今天只做这一块</div>', unsafe_allow_html=True)
    selected_label = st.radio(
        "今天的目标层次",
        ["保底", "进阶", "挑战"],
        horizontal=True,
        key="guided_today_level",
        help="先完成保底；有余力再切到进阶或挑战。",
    )
    level_key = {"保底": "minimum", "进阶": "standard", "挑战": "stretch"}[selected_label]
    level = plan["today_levels"][level_key]
    reward_points = {"保底": 20, "进阶": 40, "挑战": 60}[selected_label]
    current_points = int(st.session_state.get("reward_xp", 0))
    current_badge = reward_badge(current_points)[0]
    reward_copy = (
        '<div class="reward-card">'
        '<div class="reward-title">完成奖励</div>'
        f'<div class="reward-points">+{reward_points} 分</div>'
        f'<div class="reward-copy">先做「{html.escape(selected_label)}」目标，完成后去「我的任务」确认，积分才会到账。开始任务仍有 2 分启动奖励。</div>'
        f'<span class="reward-pill">当前 {current_points} 分 · {html.escape(current_badge)}</span>'
        '</div>'
    )
    st.markdown(reward_copy, unsafe_allow_html=True)
    if st.session_state.completed:
        st.success(f"今天这一块已经完成，+{int(st.session_state.get('last_reward_points', 0))} 分已到账。完成比完美重要。")
        render_reward_summary()
        st.markdown(
            f'<div class="simple-focus"><span class="badge">已完成</span><h2>{html.escape(level["deliverable"])}</h2><p>预计 {level["minutes"]} 分钟</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="simple-focus"><span class="badge">今日最小交付</span><h2>{html.escape(level["deliverable"])}</h2><p>预计 {level["minutes"]} 分钟 · 截止 {html.escape(str(parsed.get("deadline") or "待确认"))}</p></div>',
            unsafe_allow_html=True,
        )

    with st.expander("开始前看这里"):
        st.markdown(f"**第一步：** {html.escape(plan['today_warm_start'])}")
        st.markdown(f"**完成标准：** {html.escape(level['done_definition'])}")

    if not st.session_state.completed:
        c1, c2, c3 = st.columns(3)
        if c1.button("开始 / 继续", type="primary", use_container_width=True):
            if not st.session_state.get("start_bonus_awarded", False):
                reward_key = f"start:{st.session_state.get('current_record_id') or 'local'}:{plan.get('today_task_title') or 'task'}"
                grant_reward(2, reward_key, count_completion=False, reason="启动成功")
                st.session_state.start_bonus_awarded = True
            st.session_state.started = True
            st.session_state.stuck = False
            st.session_state.replan = None
            st.rerun()
        c2.button("去我的任务确认完成", use_container_width=True, on_click=switch_to_my_tasks)
        if c3.button("我卡住了", use_container_width=True):
            st.session_state.stuck = True
            st.rerun()

        if st.session_state.get("started") and not st.session_state.get("stuck"):
            st.progress(45, text="已经开始了，继续完成这一块")

        if st.session_state.get("stuck"):
            st.warning("先缩小范围，不要求一次做完。")
            remaining = st.slider("现在还剩多少分钟？", min_value=5, max_value=240, step=5, key="remaining_minutes")
            replanned = replan_plan(
                plan,
                completed_tasks=[],
                remaining_time=remaining,
                current_time=datetime.now(APP_TIMEZONE),
            )
            st.session_state.replan = replanned
            if replanned.get("today_tasks"):
                primary = replanned["today_tasks"][0]
                primary_minutes = int(primary.get("estimate_min") or primary.get("minutes") or 0)
                st.markdown(
                    f'<div class="simple-focus"><span class="badge">缩小后只做这个</span><h2>{html.escape(str(primary.get("title") or "任务"))}</h2><p>预计 {primary_minutes} 分钟</p></div>',
                    unsafe_allow_html=True,
                )
            if replanned.get("unscheduled_tasks"):
                st.error("这些内容今天放不下：" + "、".join(str(task.get("title") or "任务") for task in replanned["unscheduled_tasks"]))
            if replanned.get("actions"):
                st.info("可以这样处理：" + " / ".join(replanned["actions"]))

    with st.expander("每日排期与日历"):
        for index, day in enumerate(plan.get("plan_days", [])):
            day_tasks = day.get("tasks", []) if isinstance(day, dict) else []
            titles = "、".join(str(task.get("title") or "") for task in day_tasks) or "无任务"
            label = "今天" if index == 0 else f"第 {index + 1} 天"
            st.caption(f"{label}：{titles}")
        ics = generate_ics(parsed)
        if ics:
            st.download_button(
                "下载 .ics 日历",
                data=ics.encode("utf-8"),
                file_name="ddl-rescue.ics",
                mime="text/calendar",
                use_container_width=True,
            )

    st.divider()
    if st.button("换一条通知，重新开始", use_container_width=True):
        reset_guided()
        st.rerun()
