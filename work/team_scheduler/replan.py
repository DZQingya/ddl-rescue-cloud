"""对既有计划做确定性重排，不调用网络或大模型。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable


APP_TIMEZONE = timezone(timedelta(hours=8))


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed


def _task_id(task: Any) -> str:
    if isinstance(task, dict):
        return str(task.get("id", task.get("task_id", task.get("title", ""))))
    return str(task)


def _deadline_key(task: dict[str, Any], deadlines: dict[str, str], fallback: str) -> tuple[str, str]:
    value = task.get("deadline")
    if isinstance(value, dict):
        value = value.get("normalized")
    value = value or task.get("deadline_iso") or deadlines.get(str(task.get("ddl_id", ""))) or fallback
    try:
        dt = _parse_time(str(value))
        return (dt.isoformat(), str(task.get("id", "")))
    except (TypeError, ValueError):
        return ("9999-12-31T23:59:59", str(task.get("id", "")))


def _deadline_order(task: dict[str, Any], deadlines: dict[str, str], fallback: str) -> tuple[str, str]:
    # 直接按 ISO 字符串排序，避免 Windows 对 9999 年做 timestamp() 时越界。
    return _deadline_key(task, deadlines, fallback)


def _minutes(task: dict[str, Any]) -> int:
    raw = task.get(
        "estimate_min",
        task.get("remaining_estimate_min", task.get("minutes", 0)),
    )
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _extract_tasks(original: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    """读取 scheduler envelope、adapter 计划或简单 task 列表。"""
    catalog: dict[str, dict[str, Any]] = {}
    deadline_by_ddl: dict[str, str] = {}
    for key in ("deadlines", "ddls"):
        for row in original.get(key, []) or []:
            deadline = row.get("deadline", {})
            if isinstance(deadline, dict):
                deadline = deadline.get("normalized", "")
            deadline = deadline or row.get("deadline_iso", "")
            if deadline:
                deadline_by_ddl[str(row.get("id", ""))] = str(deadline)

    root_deadline = original.get("deadline", {})
    if isinstance(root_deadline, dict):
        root_deadline = root_deadline.get("normalized", "")
    root_deadline = str(root_deadline or "")

    raw_tasks = original.get("tasks", []) or []
    if isinstance(raw_tasks, list):
        for task in raw_tasks:
            if isinstance(task, dict):
                clone = deepcopy(task)
                catalog[_task_id(clone)] = clone

    plan = original.get("plan", {}) if isinstance(original.get("plan", {}), dict) else {}
    raw_days = plan.get("days") or original.get("plan_days") or original.get("days") or []
    normalized_days: list[dict[str, Any]] = []
    for day in raw_days:
        if not isinstance(day, dict):
            continue
        day_date = str(day.get("date") or day.get("day") or "")
        day_tasks: list[str] = []
        for item in day.get("tasks", []) or []:
            if isinstance(item, dict):
                task = deepcopy(item)
                task_id = _task_id(task)
                catalog.setdefault(task_id, task)
            else:
                task_id = str(item)
            if task_id:
                day_tasks.append(task_id)
        normalized_days.append({"date": day_date, "tasks": day_tasks})

    # ddl_items 是 scheduler 的聚合前输入格式。
    for index, ddl in enumerate(original.get("ddl_items", []) or [], 1):
        ddl_id = str(ddl.get("id") or f"DDL{index}")
        deadline = ddl.get("deadline", {})
        if isinstance(deadline, dict):
            deadline = deadline.get("normalized", "")
        if deadline:
            deadline_by_ddl[ddl_id] = str(deadline)
        for task in ddl.get("tasks", []) or []:
            if isinstance(task, dict):
                clone = deepcopy(task)
                clone.setdefault("ddl_id", ddl_id)
                catalog.setdefault(_task_id(clone), clone)

    if not deadline_by_ddl and root_deadline:
        deadline_by_ddl[""] = root_deadline
    return list(catalog.values()), deadline_by_ddl, normalized_days


def _shrink(task: dict[str, Any], available: int) -> dict[str, Any] | None:
    """将任务缩到可用分钟；可用量低于任务明确声明的最低工时则不虚报完成。"""
    estimate = _minutes(task)
    if estimate <= available:
        return deepcopy(task)
    if available <= 0:
        return None
    explicit_minimum = task.get("minimum_minutes", task.get("minimum_estimate_min"))
    try:
        floor = max(1, int(explicit_minimum)) if explicit_minimum is not None else 1
    except (TypeError, ValueError):
        floor = 1
    if available < floor:
        return None
    clone = deepcopy(task)
    key = "estimate_min" if "estimate_min" in clone or "minutes" not in clone else "minutes"
    original_title = str(clone.get("title") or "任务")
    clone[key] = available
    clone["scope_reduced"] = True
    clone["original_estimate_min"] = estimate
    clone["original_title"] = original_title
    clone["title"] = original_title if "（砍范围）" in original_title else f"{original_title}（砍范围）"
    clone["replan_note"] = f"工时由 {estimate} 分钟缩至 {available} 分钟，需砍减范围。"
    return clone


def replan_plan(
    original_plan: dict[str, Any],
    completed_tasks: Iterable[str | dict[str, Any]],
    remaining_time: int | float | dict[str, Any],
    current_time: str | datetime,
) -> dict[str, Any]:
    """按剩余时间重排今日任务并给出完整的新计划。

    ``remaining_time`` 可为分钟数，或 ``{"minutes": n}``。所有未完成任务
    都会进入 ``new_plan.tasks``，并且要么排入某日，要么明确列在
    ``unscheduled_tasks``，不会被静默丢弃。
    """
    if not isinstance(original_plan, dict):
        raise TypeError("original_plan 必须是字典")
    now = _parse_time(current_time)
    if isinstance(remaining_time, dict):
        remaining = remaining_time.get("minutes", remaining_time.get("remaining_minutes", 0))
    else:
        remaining = remaining_time
    try:
        budget = max(0, int(remaining))
    except (TypeError, ValueError) as exc:
        raise ValueError("remaining_time 必须是非负分钟数") from exc

    tasks, deadline_by_ddl, old_days = _extract_tasks(original_plan)
    completed_ids = {_task_id(task) for task in completed_tasks or []}
    completed_ids |= {
        _task_id(task)
        for task in tasks
        if str(task.get("status", "")).lower() in {"done", "completed"}
    }
    incomplete = [task for task in tasks if _task_id(task) not in completed_ids]
    fallback_deadline = str(original_plan.get("deadline", ""))
    if isinstance(original_plan.get("deadline"), dict):
        fallback_deadline = str(original_plan["deadline"].get("normalized", ""))

    # 阻塞任务会沿依赖链把后续任务标记为依赖阻塞，不能假装它们可排。
    unresolved_ids = {
        _task_id(task)
        for task in incomplete
        if str(task.get("status", "")).lower() in {"blocked", "stuck", "waiting"}
    }
    known_ids = {_task_id(task) for task in incomplete}
    changed = True
    while changed:
        changed = False
        for task in incomplete:
            task_id = _task_id(task)
            if task_id in unresolved_ids:
                continue
            dependencies = {str(dep) for dep in task.get("dependency", []) or []}
            if any(dep in unresolved_ids for dep in dependencies):
                unresolved_ids.add(task_id)
                changed = True

    unscheduled: list[dict[str, Any]] = []
    for task in incomplete:
        task_id = _task_id(task)
        if task_id not in unresolved_ids:
            continue
        blocked = deepcopy(task)
        blocked["replan_status"] = (
            "blocked"
            if str(task.get("status", "")).lower() in {"blocked", "stuck", "waiting"}
            else "dependency_blocked"
        )
        blocked["unscheduled_reason"] = (
            "任务被标记为阻塞，需先解除阻塞。"
            if blocked["replan_status"] == "blocked"
            else "依赖任务被阻塞，当前不能安排。"
        )
        unscheduled.append(blocked)

    schedulable = [task for task in incomplete if _task_id(task) not in unresolved_ids]
    schedulable.sort(key=lambda task: _deadline_order(task, deadline_by_ddl, fallback_deadline))

    today = now.date().isoformat()
    today_tasks: list[dict[str, Any]] = []
    excluded_optional: list[dict[str, Any]] = []
    excluded_optional_ids: set[str] = set()
    today_used = 0
    planned_ids: set[str] = set()
    for task in schedulable:
        task_id = _task_id(task)
        deadline = _deadline_key(task, deadline_by_ddl, fallback_deadline)[0]
        try:
            deadline_time = _parse_time(deadline)
        except (TypeError, ValueError):
            deadline_time = now
        if deadline_time <= now:
            missed = deepcopy(task)
            missed["replan_status"] = "overdue"
            unscheduled.append(missed)
            continue
        level = str(task.get("level", "minimum")).lower()
        is_optional = level in {"advanced", "challenge"}
        remaining_budget = budget - today_used
        estimate = _minutes(task)
        if is_optional and estimate > remaining_budget:
            excluded = deepcopy(task)
            excluded["replan_status"] = "optional_excluded"
            excluded["unscheduled_reason"] = "可选项，当前时间不足以完整完成，暂不安排。"
            excluded_optional.append(excluded)
            excluded_optional_ids.add(task_id)
            continue
        fitted = _shrink(task, remaining_budget)
        if fitted is None:
            if is_optional:
                excluded = deepcopy(task)
                excluded["replan_status"] = "optional_excluded"
                excluded_optional.append(excluded)
                excluded_optional_ids.add(task_id)
            else:
                unscheduled.append(deepcopy(task))
            continue
        fitted["replan_status"] = "scheduled_today"
        task_minutes = _minutes(fitted)
        task_start = now + timedelta(minutes=today_used)
        fitted["start_iso"] = task_start.isoformat()
        fitted["end_iso"] = (task_start + timedelta(minutes=task_minutes)).isoformat()
        today_tasks.append(fitted)
        today_used += task_minutes
        planned_ids.add(task_id)

    # 未放入今日的任务沿用原未来日期；其余显式标为未排，仍保留在总任务清单。
    future_day_map: dict[str, list[str]] = {}
    task_by_id = {_task_id(task): task for task in incomplete}
    for day in old_days:
        if day["date"] <= today:
            continue
        bucket: list[str] = []
        for task_id in day["tasks"]:
            if task_id in task_by_id and task_id not in planned_ids and task_id not in completed_ids and task_id not in excluded_optional_ids:
                deadline_value = _deadline_key(task_by_id[task_id], deadline_by_ddl, fallback_deadline)[0]
                try:
                    if _parse_time(deadline_value).date().isoformat() < day["date"]:
                        continue
                except ValueError:
                    pass
                if task_id not in bucket:
                    bucket.append(task_id)
                    planned_ids.add(task_id)
        if bucket:
            future_day_map[day["date"]] = bucket

    # 尝试依据任务自己的 DDL 兜底日期安排未来任务；只按原计划日期之后、不晚于 DDL。
    unscheduled_ids = {_task_id(task) for task in unscheduled}
    for task in incomplete:
        task_id = _task_id(task)
        if task_id in completed_ids or task_id in planned_ids or task_id in unscheduled_ids or task_id in excluded_optional_ids:
            continue
        deadline_value = _deadline_key(task, deadline_by_ddl, fallback_deadline)[0]
        try:
            due_date = _parse_time(deadline_value).date()
        except ValueError:
            unscheduled.append(deepcopy(task))
            unscheduled_ids.add(task_id)
            continue
        if due_date > now.date():
            target = due_date.isoformat()
            future_day_map.setdefault(target, []).append(task_id)
            planned_ids.add(task_id)
        else:
            unscheduled.append(deepcopy(task))
            unscheduled_ids.add(task_id)

    days = [{"date": today, "tasks": [task["id"] for task in today_tasks]}]
    days.extend({"date": day, "tasks": ids} for day, ids in sorted(future_day_map.items()))
    new_plan = {
        "days": days,
        "tasks": [deepcopy(task) for task in incomplete],
        "completed_task_ids": sorted(completed_ids),
        "unscheduled_tasks": unscheduled,
    }

    actions: list[str] = []
    if unscheduled:
        actions = ["延期", "砍范围", "求助"]
    elif any(task.get("scope_reduced") for task in today_tasks):
        actions = ["砍范围"]
    status = "needs_attention" if unscheduled else ("scope_reduced" if actions else "replanned")
    if unscheduled:
        message = "当前时间内无法安排全部必交任务；请延期、砍范围或求助。"
    elif excluded_optional:
        message = "已优先保留必交内容，暂不安排当前放不下的可选任务。"
    elif actions:
        message = "已缩小部分任务范围以适配剩余时间。"
    else:
        message = "已按最早截止时间完成重排。"
    return {
        "current_time": now.isoformat(),
        "remaining_minutes": budget,
        "today_tasks": today_tasks,
        "new_plan": new_plan,
        "unscheduled_tasks": unscheduled,
        "excluded_optional_tasks": excluded_optional,
        "excluded_optional_task_ids": sorted(excluded_optional_ids),
        "actions": actions,
        "status": status,
        "message": message,
    }
