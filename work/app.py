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
    page_title="DDL 急救站",
    page_icon="🚑",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_VERSION = "v0.6.2-final-r2"
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
<div class="hero">
  <span class="badge">赛题 2 · AI 智能体 · MVP v0.6.2-final-r2</span>
  <h1>DDL 急救站</h1>
  <p>不是提醒你 DDL，而是帮你完成今天这一块。</p>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🚑 当前版本")
    st.caption("MVP v0.6.2-final-r2 · 多DDL解析 + 团队规则 + 日期P0 + 排期可见")
    st.markdown("### AI 工作流")
    for index, step in enumerate(WORKFLOW_STEPS, start=1):
        st.markdown(f"`{index:02d}` {step}")
    st.divider()
    st.markdown("### 模型解析")
    provider_defaults = environment_defaults()
    provider_mode = st.selectbox("解析方式", ["mock", "real"], format_func=lambda x: "模拟解析" if x == "mock" else "真实模型", key="provider_mode")
    if provider_mode == "real":
        st.caption("支持 OpenAI 兼容的 Chat Completions 接口。调用失败或返回无效结构时自动回退模拟解析。")
        st.text_input("接口地址", value=provider_defaults["base_url"], key="llm_base_url", help="例如 https://api.openai.com/v1")
        st.text_input("模型名称", value=provider_defaults["model"], key="llm_model")
        st.text_input("API Key", value=provider_defaults["api_key"], type="password", key="llm_api_key")
    else:
        st.caption("当前使用本地规则模拟解析，不会调用外部服务。")
    st.divider()
    st.caption("默认使用模拟数据；真实截图请先脱敏。")

tab_capture, tab_plan, tab_action = st.tabs(["① 捕获通知", "② 复核与计划", "③ 今日行动"])

with tab_capture:
    st.markdown("#### 我的工作区")
    st.caption("保存多条通知，每条通知会拆成 DDL 卡；先载入已有通知，或在下方添加新通知。")
    if st.session_state.pop("post_save_hint", False):
        st.info("通知已保存。下一步：点上方“生成全工作台今日计划”，再选择一张 DDL 卡开始。")
    render_workspace()
    st.divider()
    st.markdown("#### 添加一条新通知")
    st.caption("贴文字即可；截图/PDF 解析是下一步。先验证：今日最小交付是否是一个真正可见的成果。")

    sample_rows = [st.columns(2), st.columns(2)]
    for index, case in enumerate(SAMPLE_CASES):
        with sample_rows[index // 2][index % 2]:
            if st.button(case["label"], use_container_width=True):
                st.session_state.notice_text = case["text"]
                st.session_state["available_minutes"] = case.get("demo_minutes", 120)
                reset_for_new_notice()
                st.rerun()

    st.markdown(
        '<div class="trust-banner"><b>只做计划和提醒：</b>不登录学习通 / 第二课堂等平台，不抓取账号，不代交作业。通知来自你粘贴的文字或截图。</div>',
        unsafe_allow_html=True,
    )

    st.text_area(
        "通知 / 作业要求",
        key="notice_text",
        height=190,
        placeholder="例如：数学分析第 3 次作业：完成习题 1-5，手写拍照上传，11月1日23:59前提交。",
    )

    if st.button("开始解析", type="primary", use_container_width=True):
        if not st.session_state.notice_text.strip():
            st.warning("先粘贴一条通知。")
        else:
            with st.spinner("正在抽取截止时间、交付物和风险…"):
                clear_editor_keys()
                parsed, provider_label, fallback_reason = parse_notice(
                    st.session_state.notice_text,
                    mode=st.session_state.get("provider_mode", "mock"),
                    base_url=st.session_state.get("llm_base_url", provider_defaults["base_url"]),
                    api_key=st.session_state.get("llm_api_key", provider_defaults["api_key"]),
                    model=st.session_state.get("llm_model", provider_defaults["model"]),
                )
                st.session_state.parsed = parsed
                st.session_state.parser_provider = provider_label
                st.session_state.parser_fallback_reason = fallback_reason
                st.session_state.plan = None
                st.session_state.started = False
                st.session_state.completed = False
                st.session_state.stuck = False
                st.session_state.current_record_id = None
                st.session_state["today_level"] = "保底"
            st.toast("解析完成。请到第二页复核字段。")

    if st.session_state.parsed:
        p = st.session_state.parsed
        st.caption(f"字段来源：{st.session_state.get('parser_provider', '模拟解析')} · 请在下一页复核模型抽取结果")
        if st.session_state.get("parser_fallback_reason"):
            st.warning(st.session_state.parser_fallback_reason)
        multi_ddls = p.get("ddl_items") or []
        if multi_ddls:
            display_items = list(multi_ddls)
        else:
            display_items = [{
                "id": "DDL1",
                "title": p["title"],
                "deadline_iso": p.get("deadline_iso"),
                "tasks": [{"title": item} for item in p.get("deliverables", [])],
            }]
        display_items.sort(
            key=lambda item: item.get("deadline_iso") or "9999-12-31T23:59:59"
        )
        st.markdown(
            '<div class="board-heading"><h3>当前通知 DDL 预览</h3><span>保存后由上方工作台统一管理</span></div>',
            unsafe_allow_html=True,
        )
        for item in display_items:
            deadline_iso = item.get("deadline_iso")
            if deadline_iso:
                try:
                    deadline_label = datetime.fromisoformat(deadline_iso).strftime("%m月%d日 %H:%M")
                except ValueError:
                    deadline_label = str(deadline_iso)
            else:
                deadline_label = "待确认"
            status_text = "预览"
            status_class = "pill-muted"
            task_titles = "、".join(
                str(task.get("title", "任务")) for task in item.get("tasks", [])
            ) or "等待确认任务"
            tags = ["通知提取", "多DDL" if len(display_items) > 1 else "单DDL"]
            if p.get("scenario") == "冲突":
                tags.append("需核对冲突")
            tag_html = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in tags)
            st.markdown(
                f"""
<div class="ddl-card">
  <div class="ddl-card-head">
    <div><h4>{html.escape(str(item.get('title', '未命名 DDL')))}</h4>
    <p>截止：{html.escape(deadline_label)}</p></div>
    <span class="pill {status_class}">{status_text}</span>
  </div>
  <div class="tag-row">{tag_html}</div>
  <p>AI 拆出的动作：{html.escape(task_titles)}</p>
  <div class="ddl-action">下一步：进入「② 复核与计划」确认字段</div>
</div>
""",
                unsafe_allow_html=True,
            )
        if not display_items:
            st.markdown(
                '<div class="ddl-card"><div class="ddl-card-head"><h4>还没有可排期的 DDL</h4><span class="pill pill-warn">待确认</span></div><p>先补全通知里的截止时间，再生成计划。</p></div>',
                unsafe_allow_html=True,
            )
        if p["risks"]:
            st.warning("发现风险：" + "；".join(item["message"] for item in p["risks"]))
        save_label = "更新到工作台" if st.session_state.get("current_record_id") else "保存到工作台"
        if st.button(save_label, type="primary", use_container_width=True, key="save_current_notice"):
            raw_text = st.session_state.get("notice_text", p.get("raw_text", ""))
            record_id = st.session_state.get("current_record_id")
            if not record_id:
                # 防止用户重新解析同一条通知后再次保存，产生重复工作台记录。
                normalized_text = str(raw_text).strip()
                existing = next(
                    (
                        item for item in list_notices()
                        if str(item.get("raw_text") or "").strip() == normalized_text
                        or (
                            str(item.get("title") or "").strip() == str(p.get("title") or "").strip()
                            and str(item.get("parsed", {}).get("deadline_iso") or "")
                            == str(p.get("deadline_iso") or "")
                        )
                    ),
                    None,
                )
                record_id = existing["id"] if existing else None
            saved = save_notice(
                p,
                raw_text=raw_text,
                record_id=record_id,
            )
            st.session_state.current_record_id = saved["id"]
            st.session_state.post_save_hint = True
            if st.session_state.get("workspace_plan") or st.session_state.get("workspace_aggregated"):
                st.session_state.workspace_plan_stale = True
            st.toast("已保存到我的 DDL 工作台")
            st.rerun()

with tab_plan:
    if not st.session_state.parsed:
        st.info("先在「① 捕获通知」里解析一条通知。")
    else:
        p = st.session_state.parsed
        st.markdown("#### 字段复核：AI 可以错，你必须能改")
        st.caption("每个字段都应能追溯原文；低置信度不要自动执行。")

        left, right = st.columns([2, 1])
        with left:
            st.text_input("标题", value=p["title"], key="title_input")
            st.text_input("截止时间", value=p["deadline"], key="deadline_input")
            st.text_area(
                "交付物（一行一个）",
                value="\n".join(p["deliverables"]),
                key="deliverables_input",
                height=110,
            )
            st.text_area(
                "材料（一行一个）",
                value="\n".join(p["materials"]),
                key="materials_input",
                height=90,
            )
        with right:
            st.metric("抽取置信度", f"{p['confidence']:.0%}")
            st.metric("风险数量", len(p["risks"]))
            st.metric("场景", p["scenario"])
            with st.expander("原文出处"):
                for span in p["source_spans"]:
                    st.caption(f"“{span}”")

        if p["risks"]:
            st.markdown("##### 风险提示")
            for risk in p["risks"]:
                fn = st.error if risk["severity"] == "high" else st.warning
                fn(f"{risk['message']}（{risk['type']}）")

        st.divider()
        st.markdown("#### 排期参数")
        available_minutes = st.slider(
            "每天可用时间（分钟）",
            min_value=30,
            max_value=240,
            value=120,
            step=15,
            key="available_minutes",
            help="按你真实可投入的时间来，不要填理想状态。",
        )
        days = st.slider("计划天数", min_value=3, max_value=14, value=7, step=1)

        if st.button("生成计划与今日最小交付", type="primary", use_container_width=True):
            edited = dict(p)
            edited["title"] = st.session_state.get("title_input", p["title"])
            edited["deadline"] = st.session_state.get("deadline_input", p["deadline"])
            edited["deadline_iso"] = deadline_to_iso(edited["deadline"])
            edited["deliverables"] = [
                line.strip()
                for line in st.session_state.get("deliverables_input", "").splitlines()
                if line.strip()
            ] or p["deliverables"]
            edited["materials"] = [
                line.strip()
                for line in st.session_state.get("materials_input", "").splitlines()
                if line.strip()
            ] or p["materials"]
            st.session_state.parsed = edited
            st.session_state.plan = build_plan(edited, available_minutes=available_minutes, days=days)
            st.session_state.started = False
            st.session_state.completed = False
            st.session_state.stuck = False
            st.session_state.replan = None
            st.session_state.remaining_minutes = max(
                5,
                min(240, int(st.session_state.plan.get("today_minutes", 30)) // 2),
            )
            st.session_state["today_level"] = "保底"
            st.toast("计划已生成。去第三页看今日最小交付。")

        if st.session_state.plan:
            plan = normalize_plan(st.session_state.plan)
            m1, m2, m3 = st.columns(3)
            m1.metric("任务总时长", f"{plan['required_minutes']} 分钟")
            m2.metric("计划可用时间", f"{plan['capacity_minutes']} 分钟")
            m3.metric("本周可行", "是" if plan["feasible"] else "否")
            engine = plan.get("scheduling_engine")
            if engine == "team_scheduler":
                engine_label = "团队确定性规则"
            elif engine == "blocked":
                engine_label = "已阻断：等待确认截止时间"
            else:
                engine_label = "兜底模拟规则"
            st.caption(f"排期引擎：{engine_label}")

            if not plan["feasible"]:
                st.error(plan["conflict_message"])
            else:
                st.success("本周容量可行。先完成今日最小交付，不追求一次做完。")
            if plan.get("unscheduled_tasks"):
                st.warning(plan.get("deferred_message"))

            st.markdown("#### 每日排期")
            if plan.get("plan_days"):
                for index, day in enumerate(plan["plan_days"]):
                    day_tasks = day.get("tasks", [])
                    titles = "、".join(html.escape(task["title"]) for task in day_tasks)
                    date_text = html.escape(str(day.get("date", "")))
                    day_label = "今天" if index == 0 else f"第 {index + 1} 天"
                    date_suffix = f" · {date_text}" if date_text else ""
                    st.markdown(
                        f"""
<div class="card">
  <h4>{day_label}{date_suffix}</h4>
  <p>{day.get('minutes', 0)} 分钟 · {len(day_tasks)} 个任务</p>
  <p>{titles}</p>
</div>
""",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("暂无可排期日期。先确认截止时间。")

            st.markdown("#### 任务拆解")
            for task in plan["tasks"]:
                st.markdown(
                    f"""
<div class="task">
  <b>{html.escape(task['title'])}</b><small>{task['minutes']} 分钟 · {html.escape(task['tag'])}</small>
  <p>启动动作：{html.escape(task['warm_start'])}</p>
  <p>完成标准：{html.escape(task['done_definition'])}</p>
</div>
""",
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"""
<div class="big-first">
  <span class="badge">今日保底 · 最小交付</span>
  <h2>{html.escape(plan['today_deliverable'])}</h2>
  <p>预计 {plan['today_minutes']} 分钟 · 启动动作：{html.escape(plan['today_warm_start'])}</p>
  <p style="margin-top:.55rem;color:#166534;">完成标准：{html.escape(plan['today_done_definition'])}</p>
</div>
""",
                unsafe_allow_html=True,
            )

            st.markdown("#### 今日三层目标")
            st.caption("完成保底就算赢；有余力再进阶或挑战。")
            level_meta = [
                ("minimum", "保底", "level-minimum", "#166534", "#dcfce7"),
                ("standard", "进阶", "level-standard", "#1d4ed8", "#dbeafe"),
                ("stretch", "挑战", "level-stretch", "#92400e", "#fef3c7"),
            ]
            level_cols = st.columns(len(SAMPLE_CASES))
            for col, (key, tag, css_class, color, bg) in zip(level_cols, level_meta):
                level = plan["today_levels"][key]
                with col:
                    st.markdown(
                        f"""
<div class="level-card {css_class}">
  <span class="level-tag" style="background:{bg};color:{color};">{tag}</span>
  <h4>{html.escape(level['deliverable'])}</h4>
  <p>预计 {level['minutes']} 分钟</p>
  <p>完成标准：{html.escape(level['done_definition'])}</p>
</div>
""",
                        unsafe_allow_html=True,
                    )

with tab_action:
    if not st.session_state.plan:
        st.info("先在「② 复核与计划」里生成计划。")
    else:
        p = st.session_state.parsed
        plan = normalize_plan(st.session_state.plan)
        st.markdown("#### 今天完成这一块")
        selected_label = st.radio(
            "今天的目标层次",
            ["保底", "进阶", "挑战"],
            horizontal=True,
            key="today_level",
        )
        level_key = {"保底": "minimum", "进阶": "standard", "挑战": "stretch"}[selected_label]
        level = plan["today_levels"][level_key]
        encouragement = {
            "保底": "完成保底就已经赢过昨天的自己。",
            "进阶": "保底完成后，再花 5 分钟检查一下。",
            "挑战": "有余力再挑战；完不成也不影响保底。",
        }
        st.caption(encouragement[selected_label])
        if not st.session_state.stuck:
            st.markdown(
                f"""
<div class="big-first">
  <span class="badge">今日目标 · {selected_label}</span>
  <h2>{html.escape(level['deliverable'])}</h2>
  <p>预计 {level['minutes']} 分钟 · 有可见成果，不是“打开文件”这种启动动作</p>
</div>
""",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"""
<div class="card">
  <h4>启动动作（不单独估时）</h4>
  <p>{html.escape(plan['today_warm_start'])}</p>
</div>
<div class="card">
  <h4>完成标准</h4>
  <p>{html.escape(level['done_definition'])}</p>
</div>
""",
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        if c1.button("我开始了", type="primary", use_container_width=True):
            st.session_state.started = True
            st.session_state.stuck = False
            st.session_state.replan = None
            st.toast("先做启动动作，然后完成这一块。")
        if c2.button("我完成了", use_container_width=True):
            st.session_state.completed = True
            st.session_state.stuck = False
            st.session_state.replan = None
            st.toast(f"完成{selected_label}目标！")
            st.balloons()
        stuck_clicked = c3.button(
            "我卡住了",
            use_container_width=True,
            disabled=st.session_state.completed,
        )
        if stuck_clicked:
            st.session_state.stuck = True
            st.rerun()

        progress = 100 if st.session_state.completed else (35 if st.session_state.started else 0)
        st.progress(progress, text=f"今日进度：{progress}% · 目标：{selected_label}")

        if st.session_state.completed:
            st.success("今天这一块已完成，卡住入口已关闭。")
        elif st.session_state.stuck:
            remaining = st.slider(
                "现在还剩多少分钟？",
                min_value=0,
                max_value=240,
                step=5,
                key="remaining_minutes",
            )
            replanned = replan_plan(
                plan,
                completed_tasks=[],
                remaining_time=remaining,
                current_time=datetime.now(APP_TIMEZONE),
            )
            st.session_state.replan = replanned
            st.warning("已按当前剩余时间重新排过，不是只给建议。")
            after_minutes = sum(
                int(task.get("estimate_min") or task.get("minutes") or 0)
                for task in replanned["today_tasks"]
            )
            st.caption(
                f"原计划今日 {plan.get('today_minutes', 0)} 分钟 → "
                f"重排后 {after_minutes} 分钟 · 剩余 {remaining} 分钟"
            )
            if replanned["today_tasks"]:
                primary = replanned["today_tasks"][0]
                primary_minutes = int(primary.get("estimate_min") or primary.get("minutes") or 0)
                st.markdown(
                    f"""
<div class="big-first">
  <span class="badge">今日目标 · 重排后</span>
  <h2>{html.escape(str(primary.get('title', '任务')))}</h2>
  <p>预计 {primary_minutes} 分钟 · 已完成重排</p>
</div>
""",
                    unsafe_allow_html=True,
                )
                st.markdown("#### 重排后的今日任务")
                for task in replanned["today_tasks"]:
                    minutes = int(task.get("estimate_min") or task.get("minutes") or 0)
                    reduced = " · 已缩小范围" if task.get("scope_reduced") else ""
                    st.markdown(f"- **{html.escape(str(task.get('title', '任务')))}** · {minutes} 分钟{reduced}")
            if replanned["unscheduled_tasks"]:
                st.error("这些任务当前放不下：" + "、".join(str(task.get("title", "任务")) for task in replanned["unscheduled_tasks"]))
            if replanned["actions"]:
                st.info("下一步可选：" + " / ".join(replanned["actions"]))
            st.caption(replanned["message"])
        if st.session_state.stuck and st.session_state.replan:
            st.markdown("#### 仍然卡住时")
            for option in plan["rescue_options"]:
                st.markdown(
                    f"""
<div class="card">
  <h4>{html.escape(option['label'])}</h4>
  <p>{html.escape(option['description'])}</p>
</div>
""",
                    unsafe_allow_html=True,
                )

        st.divider()
        st.markdown("#### 把行动带走")
        ics = generate_ics(p)
        download_col, copy_col = st.columns([1, 2])
        with download_col:
            if ics:
                st.download_button(
                    "下载 .ics 日历",
                    data=ics.encode("utf-8"),
                    file_name="ddl-rescue.ics",
                    mime="text/calendar",
                    use_container_width=True,
                )
            else:
                st.info("截止时间未确认，暂不生成日历。")
        with copy_col:
            action_card = (
                f"DDL 急救站｜今日目标：{selected_label}\n"
                f"{level['deliverable']}\n\n"
                f"预计：{level['minutes']} 分钟\n"
                f"启动动作：{plan['today_warm_start']}\n"
                f"完成标准：{level['done_definition']}\n"
                f"截止：{p['deadline']}"
            )
            st.text_area("复制给自己 / 发给同学", action_card, height=120)

        st.divider()
        st.markdown("#### 工作流复盘")
        st.markdown(
            '<div class="workflow">' + "".join(f"<span>{step}</span>" for step in p["workflow"]) + "</div>",
            unsafe_allow_html=True,
        )
        st.caption("通知抽取支持真实模型与模拟解析；排期和可行性判断仍由确定性规则完成。")
