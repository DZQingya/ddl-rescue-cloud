"""跨通知聚合接口。

入口接收已经解析为结构化字段的通知，不负责文本抽取或日期推断。
输出保留 ``ddl_items`` 供 scheduler 聚合，并将通知、DDL、任务 ID
命名空间化，避免不同通知中相同的局部 ID 冲突。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Iterable


def _normalize_deadline(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        normalized = value.get("normalized") or value.get("deadline_iso")
        if not normalized:
            return None
        result = deepcopy(value)
        result["normalized"] = str(normalized)
        result.setdefault("raw", str(normalized))
        result.setdefault("confidence", 1.0)
        result.setdefault("source_span", result["raw"])
    elif isinstance(value, str) and value.strip():
        result = {
            "raw": value,
            "normalized": value,
            "confidence": 1.0,
            "source_span": value,
        }
    else:
        return None
    parsed = _parse_iso(result["normalized"])
    result["normalized"] = parsed.isoformat()
    return result


def _parse_iso(value: str) -> datetime:
    iso_value = str(value).strip()
    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_value)
        # DDL Schema 推荐带时区；兼容旧数据时按项目默认的中国标准时间解释。
        return parsed.replace(tzinfo=timezone(timedelta(hours=8))) if parsed.tzinfo is None else parsed
    except ValueError as exc:
        raise ValueError(f"无效的截止时间 ISO 字符串：{value}") from exc


def _notification_id(notification: dict[str, Any]) -> str:
    value = notification.get("notification_id") or notification.get("id")
    source = notification.get("source")
    if not value and isinstance(source, dict):
        value = source.get("notification_id") or source.get("id")
    if value:
        return str(value).strip()
    # 无外部 ID 时用结构化内容生成稳定键；相同内容重复输入会触发重复 ID 错误。
    identity = {
        "title": notification.get("title") or (source.get("title") if isinstance(source, dict) else ""),
        "captured_at": notification.get("captured_at") or (source.get("captured_at") if isinstance(source, dict) else ""),
        "deadline": notification.get("deadline") or notification.get("deadline_iso"),
        "ddl_items": notification.get("ddl_items") or notification.get("deadlines") or [],
        "tasks": notification.get("tasks") or [],
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "N-" + hashlib.sha256(encoded).hexdigest()[:12]


def _root_deadline(notification: dict[str, Any]) -> dict[str, Any] | None:
    value = notification.get("deadline")
    if value is None:
        value = notification.get("deadline_iso")
    return _normalize_deadline(value)


def _notification_ddls(notification: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize current ddl_items, deadlines+tasks, and legacy single-DDL input."""
    global_tasks = [deepcopy(task) for task in (notification.get("tasks") or []) if isinstance(task, dict)]
    raw_ddls = notification.get("ddl_items")
    result: list[dict[str, Any]] = []

    if isinstance(raw_ddls, list) and raw_ddls:
        result = [deepcopy(item) for item in raw_ddls if isinstance(item, dict)]
    elif isinstance(notification.get("deadlines"), list) and notification["deadlines"]:
        rows = [row for row in notification["deadlines"] if isinstance(row, dict)]
        for index, row in enumerate(rows, 1):
            row_deadline = _normalize_deadline(row.get("deadline") or row.get("deadline_iso"))
            local_id = str(row.get("id") or f"DDL{index}")
            row_tasks = [task for task in (row.get("tasks") or []) if isinstance(task, dict)]
            result.append({
                "id": local_id,
                "title": str(row.get("title") or row.get("name") or f"作业 {index}"),
                "deadline": row_deadline,
                "deliverables": deepcopy(row.get("deliverables") or []),
                "materials": deepcopy(row.get("materials") or []),
                "risks": deepcopy(row.get("risks") or []),
                "tasks": row_tasks,
            })
    else:
        deadline = _root_deadline(notification)
        if deadline is None:
            raise ValueError("通知缺少有效 deadline 或 ddl_items")
        result = [{
            "id": str(notification.get("ddl_id") or "DDL1"),
            "title": str(notification.get("title") or "通知任务"),
            "deadline": deadline,
            "deliverables": deepcopy(notification.get("deliverables") or []),
            "materials": deepcopy(notification.get("materials") or []),
            "risks": [],
            "tasks": [],
        }]

    if not result:
        raise ValueError("通知没有可用的 DDL 项")
    local_ddl_ids = [str(item.get("id") or f"DDL{index}") for index, item in enumerate(result, 1)]
    if len(local_ddl_ids) != len(set(local_ddl_ids)):
        raise ValueError("同一通知内的 DDL id 必须唯一")

    ddl_by_id = {ddl_id: item for ddl_id, item in zip(local_ddl_ids, result)}
    for item, local_id in zip(result, local_ddl_ids):
        item.setdefault("id", local_id)
        item["deadline"] = _normalize_deadline(item.get("deadline") or item.get("deadline_iso"))
        if item["deadline"] is None:
            raise ValueError(f"DDL {local_id} 缺少有效截止时间")
        item["tasks"] = [deepcopy(task) for task in (item.get("tasks") or []) if isinstance(task, dict)]
        if not item["tasks"] and item.get("deliverables"):
            # 兼容旧版单通知：解析层可能只有 deliverables，没有任务数组。
            generated_tasks = []
            for task_index, deliverable in enumerate(item.get("deliverables") or [], 1):
                title = str(deliverable)
                if not title.startswith(("完成", "整理", "提交", "撰写")):
                    title = "完成" + title
                generated_tasks.append({
                    "id": f"T{task_index}",
                    "title": title,
                    "estimate_min": 30,
                    "level": "minimum",
                    "dependency": [f"T{task_index - 1}"] if task_index > 1 else [],
                })
            item["tasks"] = generated_tasks

    if global_tasks:
        if len(result) == 1:
            ddl_by_id[local_ddl_ids[0]]["tasks"].extend(global_tasks)
        else:
            for task in global_tasks:
                ddl_id = task.get("ddl_id")
                if ddl_id is None and "ddl_index" in task:
                    try:
                        ddl_id = local_ddl_ids[int(task["ddl_index"])]
                    except (ValueError, TypeError, IndexError) as exc:
                        raise ValueError(f"任务 {task.get('id', '?')} 的 ddl_index 无效") from exc
                if ddl_id is None or str(ddl_id) not in ddl_by_id:
                    raise ValueError(
                        f"多 DDL 通知中的任务 {task.get('id', '?')} 必须提供有效 ddl_id/ddl_index"
                    )
                ddl_by_id[str(ddl_id)]["tasks"].append(task)
    return result


def _as_deadline_text(deadline: Any) -> str | None:
    normalized = _normalize_deadline(deadline)
    return normalized["normalized"] if normalized else None


def aggregate_notifications(notifications: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """聚合多个结构化通知，返回 scheduler 可继续处理的统一 envelope。

    参数：通知列表。每条通知可带 ``notification_id``（优先）、``source``、
    ``ddl_items``，或兼容的 ``deadlines`` + 带 ``ddl_id`` 的全局 ``tasks``，
    也可使用旧的单 ``deadline`` + ``tasks`` 格式。

    返回：scheduler envelope，包含 namespaced ``ddl_items``、最早根级
    ``deadline``、来源列表、合并后的材料/成果/风险以及空的 ``plan``。
    输入对象不会被修改。缺失任务归属或重复通知 ID 会明确报错。
    """
    items = list(notifications)
    if not items:
        raise ValueError("notifications 至少需要包含一条通知")
    if any(not isinstance(item, dict) for item in items):
        raise TypeError("notifications 中的每一项都必须是字典")

    ids = [_notification_id(item) for item in items]
    if any(not item_id for item_id in ids):
        raise ValueError("notification_id 不能为空")
    if len(ids) != len(set(ids)):
        raise ValueError("notification_id 必须唯一；请先决定重复通知的去重策略")

    merged_ddls: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    deliverables: list[Any] = []
    materials: list[Any] = []
    risks: list[dict[str, Any]] = []
    deadline_values: list[dict[str, Any]] = []

    for notification, notification_id in zip(items, ids):
        source = notification.get("source")
        source = deepcopy(source) if isinstance(source, dict) else {}
        source.setdefault("notification_id", notification_id)
        if notification.get("title"):
            source.setdefault("title", str(notification["title"]))
        if notification.get("captured_at"):
            source.setdefault("captured_at", str(notification["captured_at"]))
        sources.append(source)

        root_risks = notification.get("risks") or []
        for risk in root_risks:
            if isinstance(risk, dict):
                item_risk = deepcopy(risk)
                item_risk.setdefault("notification_id", notification_id)
                risks.append(item_risk)

        for ddl_index, ddl in enumerate(_notification_ddls(notification), 1):
            local_ddl_id = str(ddl.get("id") or f"DDL{ddl_index}")
            qualified_ddl_id = f"{notification_id}:{local_ddl_id}"
            ddl_deadline = _normalize_deadline(ddl.get("deadline"))
            assert ddl_deadline is not None
            deadline_values.append(ddl_deadline)
            raw_tasks = ddl.get("tasks") or []
            task_records: list[tuple[str, dict[str, Any]]] = []
            local_to_global: dict[str, str] = {}
            for task_index, task in enumerate(raw_tasks, 1):
                if not isinstance(task, dict):
                    continue
                local_task_id = str(task.get("id") or f"T{task_index}")
                if local_task_id in local_to_global:
                    raise ValueError(f"DDL {local_ddl_id} 中任务 id 重复：{local_task_id}")
                global_task_id = f"{qualified_ddl_id}:{local_task_id}"
                local_to_global[local_task_id] = global_task_id
                task_records.append((local_task_id, deepcopy(task)))

            # 对每个任务应用 DDL 命名空间，并把依赖引用一并改写。
            normalized_tasks: list[dict[str, Any]] = []
            for local_task_id, task in task_records:
                dependencies = task.get("dependency") or []
                if isinstance(dependencies, str):
                    dependencies = [dependencies]
                normalized_dependencies = []
                for dependency in dependencies:
                    dep = str(dependency)
                    if dep in local_to_global:
                        normalized_dependencies.append(local_to_global[dep])
                    elif dep.startswith(f"{notification_id}:"):
                        normalized_dependencies.append(dep)
                    else:
                        normalized_dependencies.append(f"{qualified_ddl_id}:{dep}")
                task_deadline = _normalize_deadline(task.get("deadline")) or ddl_deadline
                task["id"] = local_to_global[local_task_id]
                task["ddl_id"] = qualified_ddl_id
                task["notification_id"] = notification_id
                task["deadline"] = task_deadline
                task["dependency"] = normalized_dependencies
                normalized_tasks.append(task)

            merged_ddls.append({
                "id": qualified_ddl_id,
                "local_ddl_id": local_ddl_id,
                "notification_id": notification_id,
                "title": str(ddl.get("title") or ddl.get("name") or "作业"),
                "deadline": ddl_deadline,
                "deliverables": deepcopy(ddl.get("deliverables") or []),
                "materials": deepcopy(ddl.get("materials") or []),
                "risks": deepcopy(ddl.get("risks") or []),
                "tasks": normalized_tasks,
            })
            deliverables.extend(deepcopy(ddl.get("deliverables") or []))
            materials.extend(deepcopy(ddl.get("materials") or []))
            for risk in ddl.get("risks") or []:
                if isinstance(risk, dict):
                    item_risk = deepcopy(risk)
                    item_risk.setdefault("notification_id", notification_id)
                    item_risk.setdefault("ddl_id", qualified_ddl_id)
                    risks.append(item_risk)

    earliest = min(deadline_values, key=lambda deadline: _parse_iso(deadline["normalized"]))
    captured_values = [source.get("captured_at") for source in sources if source.get("captured_at")]
    return {
        "source": {
            "type": "aggregate",
            "title": f"跨通知聚合（{len(items)} 条）",
            "captured_at": max(captured_values) if captured_values else "",
        },
        "notification_sources": sources,
        "deadline": deepcopy(earliest),
        "ddl_items": merged_ddls,
        "deliverables": deliverables,
        "materials": materials,
        "risks": risks,
        "tasks": [],
        "plan": {"capacity_min": 0, "required_min": 0, "feasible": True, "days": []},
        "status": "draft",
    }


# 简短调用名，便于接入层使用；与 aggregate_notifications 完全一致。
aggregate = aggregate_notifications


__all__ = ["aggregate_notifications", "aggregate"]
