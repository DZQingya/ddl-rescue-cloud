"""DDL 急救站确定性任务排期模块。

本模块不调用网络或大模型 API。容量及优先级参数可按业务需要修改。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any


# 默认配置：后续可在这里调整，或由项目配置层导入覆盖。
WEEKDAY_CAPACITY_MIN = 120
WEEKEND_CAPACITY_MIN = 180
PLANNING_WINDOW_DAYS = 7

LEVEL_ORDER = {"minimum": 0, "advanced": 1, "challenge": 2}
LEVEL_BONUS = {"minimum": 30, "advanced": 10, "challenge": 0}
# 兼容旧数据；新 Schema 与新案例统一使用 advanced/challenge。
LEVEL_ALIASES = {"standard": "advanced", "stretch": "challenge"}
DEADLINE_CONFIDENCE_THRESHOLD = 0.70

VAGUE_DEADLINE_PATTERNS = (
    "下周初", "下周末", "近期", "尽快", "月底", "月初", "左右", "差不多",
    "具体时间待定", "时间待定", "看通知", "另行通知", "待通知", "尽早",
)
VAGUE_FORMAT_PATTERNS = (
    "格式待定", "格式待确认", "格式不明确", "格式不清楚", "格式不详",
    "未说明格式", "格式未知", "格式另行通知", "格式看通知", "按要求提交",
)


def _parse_deadline(deadline_iso: str) -> datetime:
    """解析 ISO 截止时间；无时区时按本机本地时区处理。"""
    if not isinstance(deadline_iso, str) or not deadline_iso.strip():
        raise ValueError("deadline_iso 必须是非空 ISO 时间字符串")
    value = deadline_iso.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        deadline = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"无效的 ISO 截止时间: {deadline_iso}") from exc
    if deadline.tzinfo is None:
        # Schema 推荐带时区；缺省时区时使用系统本地时区，避免与本机“现在”比较报错。
        deadline = deadline.astimezone()
    return deadline


def _now_in_timezone(tzinfo: Any) -> datetime:
    """取得截止时间同一时区的当前时间，便于测试时替换此函数。"""
    return datetime.now(tzinfo)


def _capacity_for_day(day: date) -> int:
    return WEEKEND_CAPACITY_MIN if day.weekday() >= 5 else WEEKDAY_CAPACITY_MIN


def _canonical_level(level: Any) -> str:
    level = str(level or "advanced")
    return LEVEL_ALIASES.get(level, level)


def _deadline_object(value: Any) -> dict[str, Any] | None:
    """将 ISO 字符串或 deadline 对象统一成结构化对象。"""
    if isinstance(value, str) and value.strip():
        return {"raw": value, "normalized": value, "confidence": 1.0, "source_span": value}
    if isinstance(value, dict) and value.get("normalized"):
        return dict(value)
    return None


def _task_deadline(task: dict[str, Any], data: dict[str, Any] | None = None, fallback: str | None = None) -> str | None:
    """解析任务自己的截止时间；旧数据兼容到其 ddl_id/root deadline。"""
    direct = _deadline_object(task.get("deadline"))
    if direct:
        return str(direct["normalized"])
    if data:
        ddl_id = task.get("ddl_id")
        for entry in data.get("deadlines", []) or []:
            if str(entry.get("id", "")) == str(ddl_id):
                nested = _deadline_object(entry.get("deadline"))
                if nested:
                    return str(nested["normalized"])
    if fallback:
        return fallback
    if data:
        root_deadline = _deadline_object(data.get("deadline"))
        if root_deadline:
            return str(root_deadline["normalized"])
    return None


def aggregate_notification(data_dict: dict[str, Any]) -> dict[str, Any]:
    """將一條通知中的 ddl_items 聚合為單一 deadlines + tasks 結構。

    每個 ddl_item 都保留为一条 deadline 记录；其 tasks 合并到根 tasks，
    并附上 ddl_id 与任务级 deadline。根 deadline 取最早截止，用于兼容旧调用方。
    """
    ddl_items = data_dict.get("ddl_items")
    if not isinstance(ddl_items, list) or not ddl_items:
        return data_dict

    all_ids: list[str] = []
    normalized_items: list[tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
    for index, item in enumerate(ddl_items, start=1):
        ddl_id = str(item.get("id") or f"DDL{index}")
        deadline = _deadline_object(item.get("deadline"))
        tasks = [task for task in (item.get("tasks") or []) if isinstance(task, dict)]
        normalized_items.append((ddl_id, deadline or {}, tasks, item))
        all_ids.extend(str(task.get("id") or f"T{task_index}") for task_index, task in enumerate(tasks, start=1))

    duplicate_ids = {task_id for task_id in all_ids if all_ids.count(task_id) > 1}
    deadlines: list[dict[str, Any]] = []
    aggregated_tasks: list[dict[str, Any]] = []
    deliverables: list[Any] = list(data_dict.get("deliverables") or [])
    materials: list[Any] = list(data_dict.get("materials") or [])
    risks: list[Any] = list(data_dict.get("risks") or [])

    for ddl_id, ddl_deadline, tasks, item in normalized_items:
        if ddl_deadline:
            deadlines.append({
                "id": ddl_id,
                "title": str(item.get("title", "")),
                "deadline": ddl_deadline,
            })
        deliverables.extend(item.get("deliverables") or [])
        materials.extend(item.get("materials") or [])
        risks.extend(item.get("risks") or [])

        local_map: dict[str, str] = {}
        for task_index, task in enumerate(tasks, start=1):
            old_id = str(task.get("id") or f"T{task_index}")
            local_map[old_id] = f"{ddl_id}:{old_id}" if old_id in duplicate_ids else old_id
        for task_index, task in enumerate(tasks, start=1):
            merged = dict(task)
            old_id = str(task.get("id") or f"T{task_index}")
            merged["id"] = local_map[old_id]
            merged["dependency"] = [local_map.get(str(dep), str(dep)) for dep in (task.get("dependency") or [])]
            merged["ddl_id"] = ddl_id
            task_deadline = _deadline_object(task.get("deadline")) or (ddl_deadline or None)
            if task_deadline:
                merged["deadline"] = task_deadline
            aggregated_tasks.append(merged)

    if deadlines:
        data_dict["deadlines"] = deadlines
        earliest = min(deadlines, key=lambda entry: _parse_deadline(entry["deadline"]["normalized"]))
        data_dict["deadline"] = dict(earliest["deadline"])
    data_dict["tasks"] = aggregated_tasks
    data_dict["deliverables"] = deliverables
    data_dict["materials"] = materials
    data_dict["risks"] = risks
    data_dict.pop("ddl_items", None)
    return data_dict


def calc_capacity_for_data(data_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """为通知中的所有任务截止日期计算去重后的可用日容量。"""
    aggregate_notification(data_dict)
    fallback = (data_dict.get("deadline") or {}).get("normalized")
    capacities_by_day: dict[str, int] = {}
    seen_deadlines: set[str] = set()
    for task in data_dict.get("tasks", []) or []:
        deadline_iso = _task_deadline(task, data_dict, fallback)
        if not deadline_iso or deadline_iso in seen_deadlines:
            continue
        seen_deadlines.add(deadline_iso)
        for item in calc_capacity(deadline_iso):
            day = item["date"]
            capacities_by_day[day] = max(capacities_by_day.get(day, 0), item["capacity_min"])
    if not seen_deadlines and fallback:
        for item in calc_capacity(fallback):
            capacities_by_day[item["date"]] = item["capacity_min"]
    return [{"date": day, "capacity_min": capacity} for day, capacity in sorted(capacities_by_day.items())]


def _add_ambiguity_risks(data_dict: dict[str, Any]) -> None:
    """按可解释的固定规则生成 deadline 与格式相关歧义风险。"""
    risks = data_dict.setdefault("risks", [])
    existing = {
        (risk.get("type"), risk.get("message"))
        for risk in risks
        if isinstance(risk, dict)
    }
    deadline = data_dict.get("deadline") or {}
    raw = str(deadline.get("raw", ""))
    confidence = deadline.get("confidence")

    candidates: list[dict[str, str]] = []
    low_confidence = (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and confidence < DEADLINE_CONFIDENCE_THRESHOLD
    )
    vague_deadline = bool(raw and any(pattern in raw for pattern in VAGUE_DEADLINE_PATTERNS))
    if low_confidence or vague_deadline:
        reasons = []
        if low_confidence:
            reasons.append(
                f"识别置信度 {confidence:.2f} 低于 {DEADLINE_CONFIDENCE_THRESHOLD:.2f}"
            )
        if vague_deadline:
            reasons.append(f"原文表述可能含糊（{raw}）")
        candidates.append({
            "type": "ambiguity",
            "message": "截止时间需确认：" + "；".join(reasons) + "。",
            "severity": "medium",
        })

    unclear_format = False
    for deliverable in data_dict.get("deliverables", []) or []:
        requirements = deliverable.get("requirements", []) if isinstance(deliverable, dict) else []
        if any(
            any(pattern in str(requirement) for pattern in VAGUE_FORMAT_PATTERNS)
            for requirement in (requirements or [])
        ):
            unclear_format = True
            break
    if unclear_format:
        candidates.append({
            "type": "ambiguity",
            "message": "成果格式要求未明确，请确认文件类型、模板或排版规范。",
            "severity": "medium",
        })

    for risk in candidates:
        key = (risk["type"], risk["message"])
        if key not in existing:
            risks.append(risk)
            existing.add(key)


def calc_capacity(deadline_iso: str) -> list[dict[str, Any]]:
    """计算从今天到截止日（含）每天的默认容量。

    仅覆盖截止日前 7 天的配置窗口；如果截止更近，则从今天起计算。
    deadline 已过时返回空列表。返回元素为 {"date": YYYY-MM-DD,
    "capacity_min": 分钟}。
    """
    deadline = _parse_deadline(deadline_iso)
    now = _now_in_timezone(deadline.tzinfo)
    if now >= deadline:
        return []

    today = now.date()
    # 截止日前 7 天到截止日共 8 个日历日期，符合“截止日前7天”的窗口。
    window_start = max(today, deadline.date() - timedelta(days=PLANNING_WINDOW_DAYS))
    result: list[dict[str, Any]] = []
    current_day = window_start
    while current_day <= deadline.date():
        capacity = _capacity_for_day(current_day)
        # 截止日按截止时刻之前剩余的分钟数封顶，避免把任务安排到 deadline 之后。
        if current_day == deadline.date():
            day_start = datetime.combine(current_day, time.min, tzinfo=deadline.tzinfo)
            minutes_until_deadline = max(
                0, int((deadline - max(now, day_start)).total_seconds() // 60)
            )
            capacity = min(capacity, minutes_until_deadline)
        result.append({"date": current_day.isoformat(), "capacity_min": capacity})
        current_day += timedelta(days=1)
    return result


def _time_urgency_score(remaining_minutes: float) -> int:
    days = remaining_minutes / 1440
    if days <= 1:
        return 100
    if days <= 3:
        return 80
    if days <= 7:
        return 60
    if days <= 14:
        return 35
    return 15


def _duration_score(estimate_min: int) -> int:
    if estimate_min >= 180:
        return 100
    if estimate_min >= 90:
        return 75
    if estimate_min >= 45:
        return 50
    return 25


def calc_priority(tasks: list[dict[str, Any]], deadline_iso: str) -> list[dict[str, Any]]:
    """按各任务自己的截止时间计算确定性优先级分数。"""
    scored: list[dict[str, Any]] = []
    for task in tasks:
        item = dict(task)
        item_deadline_iso = _task_deadline(item, fallback=deadline_iso) or deadline_iso
        item_deadline = _parse_deadline(item_deadline_iso)
        now = _now_in_timezone(item_deadline.tzinfo)
        remaining = max(0.0, (item_deadline - now).total_seconds() / 60)
        urgency = _time_urgency_score(remaining)
        estimate = item.get("estimate_min", 0)
        if not isinstance(estimate, (int, float)) or isinstance(estimate, bool):
            estimate = 0
        estimate = max(0, int(estimate))
        level = _canonical_level(item.get("level", "advanced"))
        item["priority_score"] = round(
            0.6 * urgency + 0.4 * _duration_score(estimate) + LEVEL_BONUS.get(level, 0),
            2,
        )
        scored.append(item)
    return scored


def _task_sort_key(task: dict[str, Any]) -> tuple[Any, ...]:
    """同一层级内优先按截止时刻升序，再按分数、工时和 ID 稳定排序。"""
    level = _canonical_level(task.get("level", "advanced"))
    deadline_iso = _task_deadline(task)
    deadline_timestamp = _parse_deadline(deadline_iso).timestamp() if deadline_iso else float("inf")
    return (
        LEVEL_ORDER.get(level, 1),
        deadline_timestamp,
        -float(task.get("priority_score", 0)),
        -max(0, int(task.get("estimate_min", 0) or 0)),
        str(task.get("id", "")),
    )


def _ordered_by_dependencies(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """拓扑排序；循环依赖或缺失依赖保留在末尾，供排期判定为未安排。"""
    by_id = {str(task.get("id", "")): task for task in tasks}
    pending = list(sorted(tasks, key=_task_sort_key))
    ordered: list[dict[str, Any]] = []
    resolved: set[str] = set()
    known_ids = set(by_id)
    while pending:
        progress = False
        for task in list(pending):
            dependencies = [str(dep) for dep in task.get("dependency", []) or []]
            if all(dep in resolved or dep not in known_ids for dep in dependencies):
                ordered.append(task)
                resolved.add(str(task.get("id", "")))
                pending.remove(task)
                progress = True
        if not progress:
            # 剩余任务包含循环依赖，后续不会被误排。
            ordered.extend(pending)
            break
    return ordered


def schedule_tasks(data_dict: dict[str, Any]) -> dict[str, Any]:
    """按规则安排任务，并原地写入 data_dict['plan']['days']。

    使用最少负载优先的日期选择以分散任务。缺失/循环依赖的任务不会排入。
    返回同一个 data_dict，便于链式调用。
    """
    plan = data_dict.setdefault("plan", {})
    data_dict.setdefault("risks", [])
    aggregate_notification(data_dict)
    _add_ambiguity_risks(data_dict)
    deadline_iso = (data_dict.get("deadline") or {}).get("normalized")
    if not deadline_iso:
        plan["days"] = []
        plan["capacity_min"] = 0
        return data_dict

    capacities = calc_capacity_for_data(data_dict)
    remaining_capacity = {entry["date"]: entry["capacity_min"] for entry in capacities}
    daily_tasks: dict[str, list[str]] = {day: [] for day in remaining_capacity}
    daily_load: dict[str, int] = {day: 0 for day in remaining_capacity}
    day_index = {day: index for index, day in enumerate(remaining_capacity)}
    scheduled_day: dict[str, str] = {}
    tasks = data_dict.get("tasks", []) or []
    scored = calc_priority(tasks, deadline_iso)
    ordered = _ordered_by_dependencies(scored)
    scheduled: set[str] = set()
    task_capacity_by_id: dict[str, dict[str, int]] = {}
    for task in tasks:
        task_id = str(task.get("id", ""))
        task_deadline_iso = _task_deadline(task, data_dict, deadline_iso)
        if task_deadline_iso:
            task_capacity_by_id[task_id] = {
                entry["date"]: entry["capacity_min"]
                for entry in calc_capacity(task_deadline_iso)
            }

    # 明确分三阶段调度。较高层级任务不会越过前一层级的未安排任务。
    for level in ("minimum", "advanced", "challenge"):
        stage_tasks = [task for task in ordered if _canonical_level(task.get("level")) == level]
        for task in stage_tasks:
            task_id = str(task.get("id", ""))
            estimate = task.get("estimate_min", 0)
            estimate = max(0, int(estimate)) if isinstance(estimate, (int, float)) and not isinstance(estimate, bool) else 0
            dependencies = [str(dep) for dep in task.get("dependency", []) or []]
            if any(dep not in scheduled for dep in dependencies):
                continue

            earliest_index = max(
                (day_index[scheduled_day[dep]] for dep in dependencies if dep in scheduled_day),
                default=0,
            )
            candidate_days = [
                day for day in remaining_capacity
                if day_index[day] >= earliest_index
                and remaining_capacity[day] >= estimate
                and day in task_capacity_by_id.get(task_id, remaining_capacity)
                and daily_load[day] + estimate <= task_capacity_by_id.get(task_id, {}).get(day, remaining_capacity[day])
            ]
            if not candidate_days:
                continue
            chosen_day = min(candidate_days, key=lambda day: (daily_load[day], day))
            daily_tasks[chosen_day].append(task_id)
            daily_load[chosen_day] += estimate
            remaining_capacity[chosen_day] -= estimate
            scheduled.add(task_id)
            scheduled_day[task_id] = chosen_day

        # 前一层级任一任务未排入（包括单日放不下）时，不开放后续层级。
        unplaced_in_stage = [
            task for task in stage_tasks if str(task.get("id", "")) not in scheduled
        ]
        if unplaced_in_stage:
            break

    plan["days"] = [
        {"date": day, "tasks": ids}
        for day, ids in sorted(daily_tasks.items())
        if ids
    ]
    plan["capacity_min"] = sum(item["capacity_min"] for item in capacities)
    return data_dict


def detect_conflict(
    data_dict: dict[str, Any], day_capacity_list: list[dict[str, Any]]
) -> dict[str, Any]:
    """计算容量/任务工时并检测单日和全局冲突，原地更新 plan 与 risks。"""
    plan = data_dict.setdefault("plan", {})
    risks = data_dict.setdefault("risks", [])
    _add_ambiguity_risks(data_dict)
    risks = data_dict["risks"]
    tasks = data_dict.get("tasks", []) or []
    task_by_id = {str(task.get("id", "")): task for task in tasks}

    capacity_by_day = {
        str(item.get("date")): max(0, int(item.get("capacity_min", 0) or 0))
        for item in day_capacity_list
    }
    total_capacity = sum(capacity_by_day.values())
    # required_min 按全部待完成任务计算；Schema 当前没有单任务状态字段。
    total_required = sum(
        max(0, int(task.get("estimate_min", 0) or 0))
        for task in tasks
        if isinstance(task.get("estimate_min", 0), (int, float))
        and not isinstance(task.get("estimate_min", 0), bool)
    )
    plan["capacity_min"] = total_capacity
    plan["required_min"] = total_required

    # 重新计算冲突风险，避免重复调用时不断累加相同的 conflict。
    data_dict["risks"] = [risk for risk in risks if risk.get("type") != "conflict"]
    risks = data_dict["risks"]
    has_conflict = False

    daily_totals: dict[str, int] = {}
    task_day: dict[str, str] = {}
    for day_entry in plan.get("days", []) or []:
        day = str(day_entry.get("date", ""))
        day_total = 0
        for task_id in day_entry.get("tasks", []) or []:
            task_id = str(task_id)
            task_day[task_id] = day
            task = task_by_id.get(task_id)
            if task is not None:
                estimate = task.get("estimate_min", 0)
                if isinstance(estimate, (int, float)) and not isinstance(estimate, bool):
                    day_total += max(0, int(estimate))
        daily_totals[day] = daily_totals.get(day, 0) + day_total

    for day, required in sorted(daily_totals.items()):
        available = capacity_by_day.get(day, 0)
        if day not in capacity_by_day:
            has_conflict = True
            risks.append({
                "type": "conflict",
                "message": f"{day} 不在截止前有效排期窗口内，不能安排任务。",
                "severity": "high",
            })
        if required > available:
            has_conflict = True
            risks.append({
                "type": "conflict",
                "message": f"{day} 单日过载：安排 {required} 分钟，可用容量 {available} 分钟。",
                "severity": "high",
            })

    # 对已有计划复核依赖顺序，避免外部修改计划后留下不合法安排。
    for task_id, day in task_day.items():
        task = task_by_id.get(task_id)
        if task is None:
            continue
        for dependency in task.get("dependency", []) or []:
            dep_id = str(dependency)
            dep_day = task_day.get(dep_id)
            if dep_day is None or dep_day > day:
                has_conflict = True
                risks.append({
                    "type": "conflict",
                    "message": f"任务 {task_id} 的前置任务 {dep_id} 未安排或晚于该任务。",
                    "severity": "high",
                })

    if total_required > total_capacity:
        has_conflict = True
        risks.append({
            "type": "conflict",
            "message": (
                f"截止前全局工时不可行：任务需要 {total_required} 分钟，"
                f"可用容量 {total_capacity} 分钟，缺少 {total_required - total_capacity} 分钟；"
                "已触发 Rescue Mode。"
            ),
            "severity": "high",
        })

    # 另检查未排任务。容量总量足够但任务过大、依赖缺失或循环依赖时仍不可行。
    scheduled_ids = {
        str(task_id)
        for day_entry in plan.get("days", []) or []
        for task_id in (day_entry.get("tasks", []) or [])
    }
    unscheduled = [task for task in tasks if str(task.get("id", "")) not in scheduled_ids]
    if unscheduled and total_required <= total_capacity:
        has_conflict = True
        labels = ", ".join(str(task.get("id", "?")) for task in unscheduled)
        unplaced_minimum = [
            task for task in unscheduled
            if _canonical_level(task.get("level")) == "minimum"
        ]
        if unplaced_minimum:
            minimum_labels = ", ".join(str(task.get("id", "?")) for task in unplaced_minimum)
            risks.append({
                "type": "conflict",
                "message": (
                    f"保底任务 {minimum_labels} 未能排入任一日期（任务工时可能超过单日容量，"
                    f"或依赖条件未满足）；为优先保障最低完成要求，未安排进阶/挑战任务；"
                    "已触发 Rescue Mode。"
                ),
                "severity": "high",
            })
            # 保底任务专属风险已完整说明，不再添加重复的普通未排任务风险。
        else:
            unplaced_advanced = [
                task for task in unscheduled
                if _canonical_level(task.get("level")) == "advanced"
            ]
            if unplaced_advanced:
                advanced_labels = ", ".join(str(task.get("id", "?")) for task in unplaced_advanced)
                risks.append({
                    "type": "conflict",
                    "message": (
                        f"进阶任务 {advanced_labels} 未能排入任一日期；为避免越级，未安排挑战任务。"
                        "建议砍减进阶任务范围或调整计划；已触发 Rescue Mode。"
                    ),
                    "severity": "high",
                })
            else:
                risks.append({
                    "type": "conflict",
                    "message": f"以下任务未能合法排入截止前日程（可能受单日容量或依赖限制）：{labels}。",
                    "severity": "medium",
                })

    plan["feasible"] = not has_conflict
    return data_dict


if __name__ == "__main__":
    # 本地调用示例：只使用 Python 标准库，不发生网络请求。
    demo_data = {
        "deadline": {"normalized": "2026-11-02T23:59:00+08:00"},
        "tasks": [
            {"id": "T1", "title": "列提纲", "estimate_min": 30,
             "dependency": [], "level": "minimum"},
            {"id": "T2", "title": "完成初稿", "estimate_min": 90,
             "dependency": ["T1"], "level": "minimum"},
            {"id": "T3", "title": "润色排版", "estimate_min": 45,
             "dependency": ["T2"], "level": "advanced"},
        ],
        "risks": [],
        "plan": {},
    }
    capacity = calc_capacity(demo_data["deadline"]["normalized"])
    scored_tasks = calc_priority(
        demo_data["tasks"], demo_data["deadline"]["normalized"]
    )
    print("每日容量：", capacity)
    print("任务优先级：", [(t["id"], t["priority_score"]) for t in scored_tasks])
    schedule_tasks(demo_data)
    detect_conflict(demo_data, capacity)
    print("排期结果：", demo_data["plan"])
    print("风险：", demo_data["risks"])
