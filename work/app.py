from __future__ import annotations

import html
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import streamlit as st

from team_scheduler.aggregate import aggregate_notifications
from team_scheduler.replan import replan_plan
from workspace_store import (
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
    "pending": ("待排期", "pill-muted"),
    "reopened": ("待排期", "pill-muted"),
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


def _apply_ddl_status(record: dict, ddl_id: str, status: str, has_ddl_row: bool) -> None:
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

def render_workspace() -> None:
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
        m1.metric(f"{metric_prefix}汇总 DDL", len(workspace_aggregated.get("ddl_items", [])))
        m2.metric(f"{metric_prefix}总任务时长", f"{workspace_plan.get('required_minutes', 0)} 分钟")
        m3.metric(f"{metric_prefix}今日主攻", workspace_plan.get("today_deliverable", "待确认"))
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
        task_titles = "、".join(
            str(task.get("title", "任务")) for task in item.get("tasks", []) or []
        ) or "等待确认任务"
        source_title = str(record.get("title") or "未命名通知")
        suffix = record["id"] if card["card_count"] == 1 else f"{record['id']}_{ddl_id}"
        st.markdown(
            f"""
<div class="ddl-card">
  <div class="ddl-card-head"><div><h4>{html.escape(str(item.get("title") or "未命名 DDL"))}</h4><p>截止：{html.escape(_format_ddl_deadline(item))}</p></div><span class="pill {status_class}">{status_label}</span></div>
  <div class="tag-row"><span class="tag">所属通知共 {card["card_count"]} 个 DDL</span>{status_note}<span class="tag">来源：{html.escape(source_title)}</span></div>
  <p>AI 拆出的动作：{html.escape(task_titles)}</p>
</div>
""",
            unsafe_allow_html=True,
        )
        load_col, start_col, complete_col, stuck_col = st.columns([1.2, 1.0, 1.0, 1.0])
        with load_col:
            if st.button("载入编辑", key=f"workspace_load_{suffix}", use_container_width=True):
                st.session_state.notice_text = record.get("raw_text") or record.get("parsed", {}).get("raw_text") or ""
                st.session_state.parsed = deepcopy(record.get("parsed") or {})
                st.session_state.plan = None
                st.session_state.started = False
                st.session_state.completed = False
                st.session_state.stuck = False
                st.session_state.replan = None
                st.session_state.current_record_id = record["id"]
                st.rerun()
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

    st.info(_next_step_message(cards, st.session_state.get("workspace_plan_stale", False)))

    st.markdown("#### 通知管理")
    for record in records:
        record_card_count = sum(
            1 for item in cards if item["record"]["id"] == record["id"]
        )
        if st.button("删除", key=f"workspace_delete_{record['id']}", use_container_width=False):
            st.session_state.delete_confirm_id = record["id"]
            st.rerun()
        if st.session_state.get("delete_confirm_id") == record["id"]:
            st.warning(
                f"确认删除“{record.get('title') or '未命名通知'}”？"
                f"这条通知包含 {record_card_count} 个 DDL，删除后不可恢复。"
            )
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button("确认删除", key=f"workspace_delete_confirm_{record['id']}", use_container_width=True):
                    delete_notice(record["id"])
                    if st.session_state.get("workspace_plan") or st.session_state.get("workspace_aggregated"):
                        st.session_state.workspace_plan_stale = True
                    st.session_state.delete_confirm_id = None
                    if st.session_state.get("current_record_id") == record["id"]:
                        st.session_state.parsed = None
                        st.session_state.plan = None
                        st.session_state.current_record_id = None
                    st.toast("已从通知工作台删除")
                    st.rerun()
            with cancel_col:
                if st.button("取消删除", key=f"workspace_delete_cancel_{record['id']}", use_container_width=True):
                    st.session_state.delete_confirm_id = None
                    st.rerun()


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


def save_parsed_notice(parsed: dict, raw_text: str) -> str:
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
    return saved["id"]


def run_parse(raw_text: str) -> None:
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
        save_parsed_notice(parsed, text)
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
        run_parse(st.session_state.get("notice_text", ""))

    if st.session_state.pop("guided_demo_requested", False):
        run_parse(st.session_state.get("notice_text", ""))

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

    with st.expander("我保存过的任务（可选）"):
        render_workspace()

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
            run_parse(st.session_state.get("notice_text", ""))

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
            st.session_state.plan = build_plan(parsed, available_minutes=available_minutes, days=7)
            st.session_state.started = False
            st.session_state.completed = False
            st.session_state.stuck = False
            st.session_state.replan = None
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
    if st.session_state.completed:
        st.success("今天这一块已经完成。完成比完美重要。")
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
            st.session_state.started = True
            st.session_state.stuck = False
            st.session_state.replan = None
            st.rerun()
        if c2.button("我完成了", use_container_width=True):
            st.session_state.completed = True
            st.session_state.stuck = False
            st.balloons()
            st.rerun()
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
