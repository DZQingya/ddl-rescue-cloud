"""截止时间的纯函数工具：选出来的时间如何写回识别结果。

不依赖 Streamlit，方便单测，也让 app.py 瘦一点。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


APP_TIMEZONE = timezone(timedelta(hours=8))


def item_deadline_iso(item: dict) -> str | None:
    """取一个 DDL 项的截止时间 ISO，兼容 deadline 字典。"""
    if not isinstance(item, dict):
        return None
    iso = item.get("deadline_iso")
    if not iso:
        deadline = item.get("deadline")
        if isinstance(deadline, dict):
            iso = deadline.get("normalized")
    return str(iso) if iso else None


def dt_from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed.astimezone(APP_TIMEZONE)


def apply_manual_deadline(parsed: dict, deadline_at: datetime, ddl_id: str = "") -> dict:
    """把日历选出来的时间写回识别结果。

    传 ddl_id 只改那一项；不传则多 DDL 全部统一（避免半新半旧）。
    同时清掉「日期类」风险，让排期门禁打开。
    """
    parsed = dict(parsed or {})
    iso = deadline_at.isoformat()
    record = {"raw": "手动确认", "normalized": iso, "confidence": 1.0, "source_span": "手动确认"}
    items = parsed.get("ddl_items") or []
    if items:
        updated: list[Any] = []
        for item in items:
            if not isinstance(item, dict):
                updated.append(item)
                continue
            if ddl_id and str(item.get("id") or "") != ddl_id:
                updated.append(item)
                continue
            item = dict(item)
            item["deadline_iso"] = iso
            item["deadline"] = dict(record)
            item["deadline_source"] = "手动确认"
            item["deadline_basis"] = "manual"
            item["tasks"] = [
                {**task, "deadline": dict(record)}
                for task in (item.get("tasks") or [])
                if isinstance(task, dict)
            ]
            updated.append(item)
        parsed["ddl_items"] = updated
        dates = [dt_from_iso(item_deadline_iso(item)) for item in updated if isinstance(item, dict)]
        earliest = min([value for value in dates if value], default=deadline_at)
        parsed["deadline_iso"] = earliest.isoformat()
        parsed["deadline"] = earliest.strftime("%Y-%m-%d %H:%M")
        parsed["ddl_count"] = len(updated)
    else:
        parsed["deadline_iso"] = iso
        parsed["deadline"] = deadline_at.strftime("%Y-%m-%d %H:%M")
        parsed["deadline_source"] = "手动确认"
        parsed["deadline_basis"] = "manual"
        parsed["ddl_count"] = parsed.get("ddl_count") or 1
    parsed["risks"] = [
        risk for risk in (parsed.get("risks") or [])
        if not (isinstance(risk, dict) and risk.get("field") == "deadline")
    ]
    parsed["deadline_candidates"] = []
    parsed["schedule_ready"] = True
    try:
        parsed["confidence"] = max(float(parsed.get("confidence") or 0), 0.95)
    except (TypeError, ValueError):
        parsed["confidence"] = 0.95
    if parsed.get("scenario") == "模糊":
        parsed["scenario"] = "清晰"
    return parsed
