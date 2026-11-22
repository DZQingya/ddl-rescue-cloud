"""将 App 的 parsed 数据适配为 DDL 急救站 scheduler 输入。

支持旧接口 parsed.deadline_iso + tasks，也支持 parsed.ddl_items/parsed.deadlines。
本模块只转换结构，不解析通知文本、不调用网络或大模型。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:  # 支持作为 works.adapter 导入及从 works 目录直接运行测试。
    from . import scheduler
except ImportError:  # pragma: no cover - 由源码布局测试覆盖
    import scheduler  # type: ignore[no-redef]


APP_TIMEZONE = timezone(timedelta(hours=8))


def _normalize_deadline(value: Any) -> dict[str, Any] | None:
    """将 App 日期字段统一为 scheduler 的 deadline 对象。"""
    if isinstance(value, dict):
        raw = str(value.get("raw") or value.get("source_span") or value.get("normalized") or "")
        normalized = value.get("normalized") or value.get("deadline_iso")
        confidence = value.get("confidence", 0.8)
        source_span = str(value.get("source_span") or raw)
    else:
        raw = str(value or "")
        normalized = value
        confidence = 0.8
        source_span = raw
    if not normalized:
        return None
    iso_value = str(normalized).strip()
    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError as exc:
        raise ValueError(f"无效的截止时间 ISO 字符串：{normalized}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return {
        "raw": raw or iso_value,
        "normalized": parsed.isoformat(),
        "confidence": float(confidence),
        "source_span": source_span or raw or iso_value,
    }


def _app_task_minutes(task: dict[str, Any]) -> int:
    """优先取 App 保底层耗时，兼容旧任务的顶层 minutes。"""
    levels = task.get("levels") or {}
    minimum = levels.get("minimum") if isinstance(levels, dict) else None
    value = minimum.get("minutes") if isinstance(minimum, dict) else task.get("minutes", task.get("estimate_min", 0))
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_deliverables(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, dict):
            result.append({
                "name": str(item.get("name") or item.get("title") or "作业成果"),
                "requirements": list(item.get("requirements") or []),
            })
        else:
            result.append({"name": str(item), "requirements": []})
    return result


def _deadline_from_app_item(item: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any] | None:
    deadline_value = item.get("deadline")
    if isinstance(deadline_value, dict):
        deadline = _normalize_deadline(deadline_value)
        if deadline:
            return deadline
    if item.get("deadline_iso"):
        return _normalize_deadline({
            "raw": item.get("deadline_source") or item.get("deadline"),
            "normalized": item.get("deadline_iso"),
            "confidence": item.get("confidence", 0.8),
            "source_span": item.get("deadline_source") or item.get("deadline"),
        })
    try:
        deadline = _normalize_deadline(deadline_value)
    except ValueError:
        deadline = None
    if deadline:
        return deadline
    return fallback


def _planning_now() -> datetime:
    """使用 scheduler 的时钟入口，便于测试冻结时间。"""
    try:
        return scheduler._now_in_timezone(APP_TIMEZONE)
    except Exception:  # pragma: no cover - scheduler 时钟不可用时退回系统时钟
        return datetime.now(APP_TIMEZONE)


def _is_expired(deadline: dict[str, Any] | None, now: datetime) -> bool:
    if not deadline:
        return False
    parsed = datetime.fromisoformat(str(deadline["normalized"]))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed < now


def app_parsed_to_ddl_items(
    parsed: dict[str, Any],
    tasks: list[dict[str, Any]] | None = None,
    *,
    include_expired: bool = True,
) -> list[dict[str, Any]]:
    """将 App 解析结果转换为 scheduler 接受的 `ddl_items`。

    多 DDL 时优先使用每个 `ddl_items[].tasks`；也可传入全局 tasks，
    但每项任务必须带 `ddl_id` 或有效 `ddl_index`，避免静默丢弃/错配。
    单 DDL 的旧 `deadline_iso` + tasks 接口保持兼容。
    """
    if tasks is None:
        tasks = parsed.get("tasks")
    root_deadline = _deadline_from_app_item(parsed)
    raw_items = parsed.get("ddl_items")
    if isinstance(raw_items, list) and raw_items:
        app_items = [dict(item) for item in raw_items if isinstance(item, dict)]
    elif isinstance(parsed.get("deadlines"), list) and parsed["deadlines"]:
        app_items = []
        for item in parsed["deadlines"]:
            if not isinstance(item, dict):
                continue
            nested = dict(item)
            if isinstance(nested.get("deadline"), dict):
                nested["deadline"] = nested["deadline"]
            app_items.append(nested)
    else:
        app_items = [{
            "id": str(parsed.get("ddl_id") or "DDL1"),
            "title": str(parsed.get("title") or "校园通知"),
            "deadline": root_deadline,
            "deliverables": parsed.get("deliverables") or [],
            "materials": parsed.get("materials") or [],
            "risks": parsed.get("risks") or [],
            "tasks": [],
        }]

    if not app_items:
        return []

    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(app_items, start=1):
        ddl_id = str(item.get("id") or f"DDL{index}")
        deadline = _deadline_from_app_item(
            item,
            root_deadline if len(app_items) == 1 else None,
        )
        if deadline is None:
            if len(app_items) == 1 and root_deadline is None:
                return []
            raise ValueError(f"DDL {ddl_id} 缺少有效截止时间")
        normalized_items.append({
            "id": ddl_id,
            "title": str(item.get("title") or item.get("name") or f"作业 {index}"),
            "deadline": deadline,
            "deliverables": _as_deliverables(item.get("deliverables") or []),
            "materials": [str(material) for material in (item.get("materials") or [])],
            "risks": [risk for risk in (item.get("risks") or []) if isinstance(risk, dict)],
            "tasks": [dict(task) for task in (item.get("tasks") or []) if isinstance(task, dict)],
        })

    if not include_expired:
        now = _planning_now()
        active_items: list[dict[str, Any]] = []
        for item in normalized_items:
            if _is_expired(item.get("deadline"), now):
                continue
            active_tasks: list[dict[str, Any]] = []
            for task in item.get("tasks") or []:
                task_deadline = _deadline_from_app_item(task, item.get("deadline"))
                if _is_expired(task_deadline, now):
                    continue
                active_tasks.append(task)
            item["tasks"] = active_tasks
            active_items.append(item)
        normalized_items = active_items
        if not normalized_items:
            return []

    if tasks:
        if len(normalized_items) == 1:
            normalized_items[0]["tasks"].extend(dict(task) for task in tasks if isinstance(task, dict))
        else:
            item_by_id = {item["id"]: item for item in normalized_items}
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                ddl_id = task.get("ddl_id")
                if ddl_id is None and "ddl_index" in task:
                    try:
                        ddl_id = normalized_items[int(task["ddl_index"])]["id"]
                    except (ValueError, TypeError, IndexError):
                        raise ValueError(f"任务 {task.get('id', '?')} 的 ddl_index 无效")
                if ddl_id is None or str(ddl_id) not in item_by_id:
                    raise ValueError(
                        f"通知包含多个 DDL，任务 {task.get('id', '?')} 必须提供有效 ddl_id/ddl_index"
                    )
                item_by_id[str(ddl_id)]["tasks"].append(dict(task))

    multiple_ddl = len(normalized_items) > 1
    output: list[dict[str, Any]] = []
    for item in normalized_items:
        ddl_id = item["id"]
        source_tasks = item["tasks"]
        id_map: dict[str, str] = {}
        for index, task in enumerate(source_tasks, start=1):
            old_id = str(task.get("id") or f"T{index}")
            if multiple_ddl:
                # aggregate 输出已经带命名空间时保持原 ID，避免二次前缀。
                id_map[old_id] = old_id if old_id.startswith(f"{ddl_id}:") else f"{ddl_id}:{old_id}"
            else:
                id_map[old_id] = old_id

        last_task_by_tag: dict[str, str] = {}
        scheduler_tasks: list[dict[str, Any]] = []
        for index, task in enumerate(source_tasks, start=1):
            old_id = str(task.get("id") or f"T{index}")
            task_id = id_map[old_id]
            tag = str(task.get("tag", "通用"))
            explicit_dependencies = task.get("dependency")
            if explicit_dependencies is not None:
                dependencies = [id_map.get(str(dep), str(dep)) for dep in explicit_dependencies]
            else:
                dependencies = [last_task_by_tag[tag]] if tag in last_task_by_tag else []

            task_deadline = _deadline_from_app_item(task, item["deadline"])
            scheduler_tasks.append({
                "id": task_id,
                "title": str(task.get("title") or "任务"),
                "estimate_min": _app_task_minutes(task),
                "dependency": dependencies,
                "first_step": str(task.get("warm_start") or task.get("first_step") or "打开任务要求。"),
                "level": "minimum",
                "ddl_id": ddl_id,
                "deadline": task_deadline,
                "priority": str(task.get("priority") or "normal").lower(),
                "manual_priority": bool(task.get("manual_priority")),
                "manual_order": task.get("manual_order"),
            })
            last_task_by_tag[tag] = task_id

        output.append({**item, "tasks": scheduler_tasks})
    return output


def app_parsed_to_scheduler_input(
    parsed: dict[str, Any],
    tasks: list[dict[str, Any]] | None = None,
    *,
    include_expired: bool = True,
) -> dict[str, Any] | None:
    """返回可直接传给 scheduler.schedule_tasks 的完整输入对象。

    没有可用截止时间时返回 None，与旧 schedule_plan 的回退约定一致。
    """
    try:
        ddl_items = app_parsed_to_ddl_items(parsed, tasks, include_expired=include_expired)
    except ValueError:
        raise
    if not ddl_items:
        return None
    earliest = min(
        (item["deadline"] for item in ddl_items),
        key=lambda item: datetime.fromisoformat(item["normalized"]),
    )
    now = datetime.now(APP_TIMEZONE).isoformat()
    return {
        "source": {
            "type": str(parsed.get("source_type") or "text"),
            "title": str(parsed.get("title") or "校园通知"),
            "captured_at": str(parsed.get("captured_at") or now),
        },
        "deadline": dict(earliest),
        "ddl_items": ddl_items,
        "deliverables": [],
        "materials": [],
        "risks": [risk for risk in (parsed.get("risks") or []) if isinstance(risk, dict)],
        "tasks": [],
        "plan": {"capacity_min": 0, "required_min": 0, "feasible": True, "days": []},
        "status": str(parsed.get("status") or "draft"),
    }


def _source_tasks_by_scheduler_id(
    parsed: dict[str, Any],
    supplied_tasks: list[dict[str, Any]] | None,
    ddl_items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """保留 App 原始任务对象，供旧 plan_days 返回结构使用。"""
    raw_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    raw_items = parsed.get("ddl_items") or []
    multiple = len(ddl_items) > 1
    for index, item in enumerate(raw_items, start=1):
        ddl_id = str(item.get("id") or f"DDL{index}")
        for task_index, task in enumerate(item.get("tasks") or [], start=1):
            if isinstance(task, dict):
                raw_id = str(task.get("id") or f"T{task_index}")
                raw_by_key[(ddl_id, raw_id)] = task

    source_tasks = supplied_tasks if supplied_tasks is not None else parsed.get("tasks")
    if source_tasks:
        for task_index, task in enumerate(source_tasks, start=1):
            if not isinstance(task, dict):
                continue
            if len(ddl_items) == 1:
                ddl_id = ddl_items[0]["id"]
            else:
                ddl_id = task.get("ddl_id")
                if ddl_id is None and "ddl_index" in task:
                    try:
                        ddl_id = ddl_items[int(task["ddl_index"])]["id"]
                    except (ValueError, TypeError, IndexError):
                        continue
            if ddl_id is not None:
                raw_id = str(task.get("id") or f"T{task_index}")
                raw_by_key[(str(ddl_id), raw_id)] = task

    result: dict[str, dict[str, Any]] = {}
    for item in ddl_items:
        ddl_id = str(item["id"])
        for task in item.get("tasks", []):
            scheduler_id = str(task["id"])
            raw_id = scheduler_id[len(ddl_id) + 1:] if multiple and scheduler_id.startswith(f"{ddl_id}:") else scheduler_id
            original = raw_by_key.get((ddl_id, raw_id), {})
            app_task = dict(original)
            app_task.setdefault("id", scheduler_id)
            app_task.setdefault("title", task["title"])
            app_task.setdefault("minutes", task["estimate_min"])
            app_task.setdefault("warm_start", task["first_step"])
            app_task.setdefault("tag", "通用")
            app_task["ddl_id"] = ddl_id
            app_task["deadline"] = dict(task["deadline"])
            result[scheduler_id] = app_task
    return result


def schedule_plan(
    parsed: dict[str, Any],
    tasks: list[dict[str, Any]] | None = None,
    available_minutes: int = 120,
    days: int = 7,
) -> dict[str, Any] | None:
    """旧单 deadline 调用签名兼容，并支持多 DDL App 输入。"""
    ddl_items = app_parsed_to_ddl_items(parsed, tasks, include_expired=False)
    if not ddl_items:
        return None
    app_task_by_id = _source_tasks_by_scheduler_id(parsed, tasks, ddl_items)
    data = app_parsed_to_scheduler_input(parsed, tasks, include_expired=False)
    if data is None:
        return None

    old_weekday = scheduler.WEEKDAY_CAPACITY_MIN
    old_weekend = scheduler.WEEKEND_CAPACITY_MIN
    old_window = scheduler.PLANNING_WINDOW_DAYS
    try:
        scheduler.WEEKDAY_CAPACITY_MIN = max(1, int(available_minutes))
        scheduler.WEEKEND_CAPACITY_MIN = min(
            240, max(int(available_minutes), round(int(available_minutes) * 1.5))
        )
        scheduler.PLANNING_WINDOW_DAYS = max(1, int(days) - 1)
        capacities = scheduler.calc_capacity_for_data(data)
        scheduler.schedule_tasks(data)
        scheduler.detect_conflict(data, capacities)
    finally:
        scheduler.WEEKDAY_CAPACITY_MIN = old_weekday
        scheduler.WEEKEND_CAPACITY_MIN = old_weekend
        scheduler.PLANNING_WINDOW_DAYS = old_window

    plan_days = []
    for index, day in enumerate(data["plan"].get("days", [])):
        output_tasks = [app_task_by_id[task_id] for task_id in day["tasks"] if task_id in app_task_by_id]
        plan_days.append({
            "day": "今天" if index == 0 else day["date"],
            "date": day["date"],
            "tasks": output_tasks,
            "minutes": sum(int(task.get("minutes", task.get("estimate_min", 0)) or 0) for task in output_tasks),
        })
    risks = data.get("risks", [])
    conflict_message = "；".join(
        risk.get("message", "") for risk in risks if risk.get("type") == "conflict"
    )
    return {
        "plan_days": plan_days,
        "required_minutes": data["plan"]["required_min"],
        "capacity_minutes": data["plan"]["capacity_min"],
        "feasible": data["plan"]["feasible"],
        "conflict_message": conflict_message,
        "risks": risks,
        "scheduler_plan": data["plan"],
    }
