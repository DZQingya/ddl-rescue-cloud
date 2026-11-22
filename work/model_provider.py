"""真实模型接入（OpenAI 兼容接口），失败自动回退本地规则。

两种返回结构都认：
1. 简版（与手机端 v1.1 一致）：title / deadline / deliverables / ddl_items / notes / confidence；
2. 契约版：ddls / tasks / clarifications（老提示词与 group1 语料仍在用）。

解析失败不抛异常，一律回退 ``mock_engine.parse_notice``，并把原因带回去给界面显示。
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

import llm_settings
from mock_engine import build_ddl_item
from mock_engine import parse_notice as parse_notice_mock


APP_TIMEZONE = timezone(timedelta(hours=8))
QA_DIR = Path(__file__).resolve().parent / "qa"
PROMPT_PATH = QA_DIR / "simple-extraction-prompt.md"
LEGACY_PROMPT_PATH = QA_DIR / "group1-ai-extraction-prompt.md"

RULES_LABEL = "本地规则"


class ProviderError(RuntimeError):
    pass


def _default_system_prompt() -> str:
    return (
        "你是校园通知解析器。只输出一个 JSON 对象，字段为 "
        "title、deadline、deadline_source、deliverables、materials、ddl_items、notes、confidence。"
        "没有明确日期时 deadline 必须为 null，不要编造；只说日期没说时间按当天 23:59；"
        "有 2 个以上不同截止时间时 ddl_items 至少 2 项，否则给空数组。"
    )


def _system_prompt(extra: str = "") -> str:
    try:
        text = PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        text = _default_system_prompt()
    if extra:
        text = f"{text}\n\n补充要求：{extra}"
    return text


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _require_list(value: Any, name: str) -> list:
    if not isinstance(value, list):
        raise ProviderError(f"{name} 必须是数组")
    return value


def _check_enum(value: Any, name: str, allowed: set[str]) -> None:
    if value is not None and value not in allowed:
        raise ProviderError(f"{name} 非法：{value}")


def _check_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProviderError(f"{name} 必须是字符串数组")
    return value


# --------------------------------------------------------------------------- #
# 时间归一
# --------------------------------------------------------------------------- #
def _normalize_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ProviderError("deadline_iso 必须是 ISO 字符串或 null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderError(f"无效的 deadline_iso：{value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed.astimezone(APP_TIMEZONE).isoformat()


_TIME_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")
_DATE_ONLY = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_NULL_WORDS = {"", "null", "none", "unknown", "n/a", "未知", "待确认", "待定", "无", "-"}


def coerce_deadline(value: Any) -> datetime | None:
    """把模型给的时间字符串统一成 datetime；给不出就 None，绝不猜。

    只说日期没说时间，按当天 23:59（与规则引擎、手机端一致）。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=APP_TIMEZONE)
    text = str(value).strip()
    if text.lower() in _NULL_WORDS:
        return None
    cleaned = text.replace("Z", "+00:00").replace("/", "-")
    cleaned = cleaned.replace("年", "-").replace("月", "-").replace("日", " ").strip()
    if _DATE_ONLY.match(cleaned):
        try:
            return datetime.strptime(cleaned, "%Y-%m-%d").replace(
                hour=23, minute=59, tzinfo=APP_TIMEZONE
            )
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=APP_TIMEZONE)
        return parsed.astimezone(APP_TIMEZONE)
    except ValueError:
        pass
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text.replace("/", "-"), fmt).replace(tzinfo=APP_TIMEZONE)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# 契约版（ddls / tasks / clarifications）
# --------------------------------------------------------------------------- #
def _deadline(raw: Any, iso: Any) -> dict[str, Any] | None:
    normalized = _normalize_iso(iso)
    if normalized is None:
        return None
    source = str(raw or normalized)
    return {
        "raw": source,
        "normalized": normalized,
        "confidence": 0.8,
        "source_span": source,
    }


def _validate_legacy(value: dict[str, Any], source_text: str) -> dict[str, Any]:
    required = ("title", "deadline", "deadline_iso", "deliverables", "materials", "risks")
    if any(key not in value for key in required):
        raise ProviderError("模型返回字段不完整")
    if not isinstance(value["deliverables"], list) or not isinstance(value["materials"], list):
        raise ProviderError("deliverables/materials 必须为数组")
    if not isinstance(value["risks"], list):
        raise ProviderError("risks 必须为数组")
    result = dict(value)
    result["raw_text"] = source_text
    result.setdefault("workflow", [])
    result.setdefault("confidence", 0.6)
    result.setdefault("schedule_ready", bool(result.get("deadline_iso")))
    result.setdefault("scenario", "普通")
    result.setdefault("ddl_items", [])
    result.setdefault("ddl_count", len(result["ddl_items"]) or (1 if result.get("deadline_iso") else 0))
    result.setdefault("deadline_basis", "model")
    result.setdefault("deadline_source", "模型抽取，需人工复核")
    result.setdefault("source_spans", [source_text[:160]] if source_text else [])
    result.setdefault("engine", "llm")
    return result


def _validate_contract(value: dict[str, Any], source_text: str) -> dict[str, Any]:
    raw_ddls = _require_list(value["ddls"], "ddls")
    raw_tasks = _require_list(value["tasks"], "tasks")
    clarifications = _require_list(value["clarifications"], "clarifications")
    if not raw_ddls:
        raise ProviderError("模型没有返回任何 ddls")

    ddl_ids: list[str] = []
    internal_ddls: list[dict[str, Any]] = []
    allowed_ddl_status = {"pending", "active", "stuck", "done", "reopened"}
    for index, item in enumerate(raw_ddls, 1):
        if not isinstance(item, dict):
            raise ProviderError("ddls 每项必须是对象")
        required_ddl = (
            "id", "notice_id", "title", "deadline_text", "deadline_iso",
            "requirements", "submission_channel", "ddl_status", "primary",
        )
        if any(key not in item for key in required_ddl):
            raise ProviderError("ddls 字段不完整")
        ddl_id = str(item["id"]).strip()
        if not ddl_id:
            raise ProviderError("ddl.id 不能为空")
        if ddl_id in ddl_ids:
            raise ProviderError(f"DDL id 重复：{ddl_id}")
        ddl_ids.append(ddl_id)
        _check_enum(item.get("ddl_status"), "ddl_status", allowed_ddl_status)
        if item.get("primary") is not None and not isinstance(item.get("primary"), bool):
            raise ProviderError("primary 必须是 true/false/null")
        requirements = _check_string_list(item.get("requirements"), "requirements")
        deadline = _deadline(item.get("deadline_text"), item.get("deadline_iso"))
        internal_ddls.append({
            "id": ddl_id,
            "notice_id": str(item.get("notice_id") or "N1"),
            "title": str(item.get("title") or f"作业 {index}"),
            "deadline": deadline,
            "deadline_iso": deadline["normalized"] if deadline else None,
            "deadline_text": item.get("deadline_text"),
            "requirements": requirements,
            "submission_channel": item.get("submission_channel"),
            "ddl_status": item.get("ddl_status"),
            "primary": item.get("primary"),
            "tasks": [],
            "deliverables": [str(item.get("title") or f"作业 {index}")],
            "materials": [],
            "risks": [],
        })

    by_id = {item["id"]: item for item in internal_ddls}
    task_ids: set[str] = set()
    task_by_ddl: dict[str, dict[str, dict[str, Any]]] = {ddl_id: {} for ddl_id in by_id}
    internal_tasks: list[dict[str, Any]] = []
    allowed_task_status = {"pending", "in_progress", "blocked", "done", "unknown"}
    allowed_priority = {"high", "normal", "low"}
    for index, task in enumerate(raw_tasks, 1):
        if not isinstance(task, dict):
            raise ProviderError("tasks 每项必须是对象")
        required_task = ("id", "notice_id", "ddl_id", "title", "priority", "status", "dependency")
        if any(key not in task for key in required_task):
            raise ProviderError("tasks 字段不完整")
        ddl_id = str(task.get("ddl_id") or "")
        if ddl_id not in by_id:
            raise ProviderError(f"任务 {task.get('id', index)} 的 ddl_id 不存在")
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            raise ProviderError("task.id 不能为空")
        if task_id in task_ids:
            raise ProviderError(f"task id 重复：{task_id}")
        task_ids.add(task_id)
        if str(task.get("notice_id") or "") != by_id[ddl_id]["notice_id"]:
            raise ProviderError(f"任务 {task_id} 的 notice_id 与所属 DDL 不一致")
        _check_enum(task.get("priority"), "priority", allowed_priority)
        _check_enum(task.get("status"), "task.status", allowed_task_status)
        dependency = _check_string_list(task.get("dependency"), "dependency")
        normalized_task = {
            "id": task_id,
            "notice_id": str(task["notice_id"]),
            "ddl_id": ddl_id,
            "title": str(task.get("title") or "任务"),
            "priority": task.get("priority"),
            "status": task.get("status"),
            "dependency": dependency,
            "estimate_min": 30,
            "level": "minimum",
            "warm_start": "打开任务要求。",
            "done_definition": "完成这个任务块。",
        }
        by_id[ddl_id]["tasks"].append(normalized_task)
        task_by_ddl[ddl_id][task_id] = normalized_task
        internal_tasks.append(normalized_task)

    for ddl_id, ddl_tasks in task_by_ddl.items():
        for task in ddl_tasks.values():
            for dependency in task["dependency"]:
                if dependency == task["id"]:
                    raise ProviderError(f"任务 {task['id']} 不能依赖自身")
                if dependency not in ddl_tasks:
                    raise ProviderError(f"任务 {task['id']} 的依赖 {dependency} 不在同一 DDL 内")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ProviderError(f"DDL {ddl_id} 存在循环依赖")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in ddl_tasks[task_id]["dependency"]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in ddl_tasks:
            visit(task_id)

    deadlines = [item["deadline"]["normalized"] for item in internal_ddls if item.get("deadline")]
    earliest = min(deadlines) if deadlines else None
    risks = []
    for item in clarifications:
        if not isinstance(item, dict):
            raise ProviderError("clarifications 每项必须是对象")
        risks.append({
            "type": "ambiguity",
            "message": f"{item.get('field', '字段')}：{item.get('reason', '需要人工确认')}",
            "severity": "medium",
            "notice_id": item.get("notice_id"),
            "ddl_id": item.get("ddl_id"),
            "field": item.get("field"),
        })
    first_title = internal_ddls[0]["title"] if internal_ddls else "通知任务"
    return {
        "title": first_title,
        "deadline": {"normalized": earliest} if earliest else "待确认",
        "deadline_iso": earliest,
        "deliverables": [item["title"] for item in internal_ddls],
        "materials": [],
        "risks": risks,
        "raw_text": source_text,
        "workflow": [],
        "confidence": 0.7,
        "schedule_ready": bool(earliest),
        "scenario": "清晰" if earliest else "模糊",
        "ddl_items": internal_ddls,
        "ddl_count": len(internal_ddls),
        "tasks": internal_tasks,
        "deadline_basis": "model",
        "deadline_source": "模型抽取，需人工复核",
        "source_spans": [source_text[:160]] if source_text else [],
        "engine": "llm",
    }


# --------------------------------------------------------------------------- #
# 简版（手机端 v1.1 的结构）
# --------------------------------------------------------------------------- #
def _validate_simple(value: dict[str, Any], source_text: str) -> dict[str, Any]:
    base = parse_notice_mock(source_text)

    title = str(value.get("title") or "").strip()
    if not title or len(title) > 60:
        title = base["title"]

    items: list[tuple[str, datetime, list[str], list[str]]] = []
    for raw_item in _as_list(value.get("ddl_items")):
        if not isinstance(raw_item, dict):
            continue
        item_title = str(raw_item.get("title") or "").strip()
        item_deadline = coerce_deadline(raw_item.get("deadline"))
        if not item_title or item_deadline is None:
            continue
        items.append((
            item_title,
            item_deadline,
            _string_list(raw_item.get("deliverables")),
            _string_list(raw_item.get("materials")),
        ))

    deadline_at = coerce_deadline(value.get("deadline"))
    if deadline_at is None and items:
        deadline_at = min(item[1] for item in items)
    multi = len(items) >= 2

    risks: list[dict[str, Any]] = []
    blocking = 0
    if deadline_at is None:
        risks.append({
            "type": "ambiguity",
            "field": "deadline",
            "severity": "high",
            "message": "大模型也没能从原文读出明确日期，需要手动确认截止时间。",
        })
        blocking += 1

    notes = str(value.get("notes") or "").strip()
    if notes:
        risks.append({
            "type": "note",
            "field": "other",
            "severity": "medium",
            "message": f"模型提示：{notes}",
        })

    for risk in base.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        if risk.get("field") == "deadline":
            continue
        if any(existing["message"] == risk.get("message") for existing in risks):
            continue
        risks.append(risk)
        if risk.get("severity") == "high":
            blocking += 1

    ddl_items: list[dict[str, Any]] = []
    if multi:
        for index, (item_title, item_deadline, item_deliverables, item_materials) in enumerate(items, start=1):
            ddl_items.append(build_ddl_item(
                item_title,
                item_deadline,
                item_deliverables or [f"完成{item_title}"],
                deliverables=item_deliverables or [item_title],
                materials=item_materials,
                source="大模型解析",
                basis="model",
                ddl_id=f"DDL{index}",
            ))
        if len({item["deadline_iso"] for item in ddl_items}) < len(ddl_items):
            risks.append({
                "type": "conflict",
                "field": "other",
                "severity": "medium",
                "message": "模型给出多个交付物落在同一截止时刻，确认是否能同时完成。",
            })

    deliverables = _string_list(value.get("deliverables"))
    if multi:
        deliverables = list(dict.fromkeys([item["title"] for item in ddl_items] + deliverables))
    if not deliverables:
        deliverables = base.get("deliverables") or []

    materials = list(dict.fromkeys(_string_list(value.get("materials")) + (base.get("materials") or [])))

    try:
        confidence = float(value.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.85
    if not 0 <= confidence <= 1:
        confidence = 0.85
    if blocking:
        confidence = min(confidence, 0.6)

    deadline_text = deadline_at.strftime("%Y-%m-%d %H:%M") if deadline_at else "待确认"
    return {
        "title": title,
        "raw_text": source_text,
        "scenario": "模糊" if deadline_at is None else ("多 DDL" if multi else "清晰"),
        "deadline": deadline_text,
        "deadline_iso": deadline_at.isoformat() if deadline_at else None,
        "deadline_source": str(value.get("deadline_source") or "大模型解析"),
        "deadline_basis": "model" if deadline_at else "none",
        "deadline_candidates": [],
        "deadline_window": base.get("deadline_window"),
        "schedule_ready": deadline_at is not None,
        "deliverables": deliverables,
        "materials": materials,
        "risks": risks,
        "confidence": confidence,
        "ddl_count": len(ddl_items) if multi else (1 if deadline_at else 0),
        "ddl_items": ddl_items,
        "source_spans": list(dict.fromkeys(["大模型解析", source_text[:90]] + (base.get("source_spans") or []))),
        "workflow": ["大模型抽取", "校验日期", "与规则结果对齐", "冲突检测", "任务拆解", "人工确认"],
        "engine": "llm",
    }


def _validate_result(value: Any, source_text: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderError("模型返回内容不是 JSON 对象")
    contract_keys = ("ddls", "tasks", "clarifications")
    present = [key for key in contract_keys if key in value]
    if present:
        if len(present) != len(contract_keys):
            raise ProviderError("模型返回必须同时包含 ddls、tasks、clarifications")
        return _validate_contract(value, source_text)
    if any(key in value for key in ("title", "deadline", "deliverables", "ddl_items")):
        return _validate_simple(value, source_text)
    return _validate_legacy(value, source_text)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def extract_json(text: str) -> Any:
    """模型经常把 JSON 包在 ```json 里，这里统一剥掉再解析。"""
    raw = str(text or "").strip()
    if not raw:
        raise ProviderError("模型返回为空")
    raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw).strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ProviderError(f"模型返回的不是 JSON：{raw[:120]}")
    body = raw[start:end + 1]
    try:
        return json.loads(body)
    except ValueError:
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", body))
        except ValueError as exc:
            raise ProviderError(f"模型返回的 JSON 解析失败：{body[:120]}") from exc


def _content_of(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        if isinstance(first.get("text"), str):
            return first["text"]
    for key in ("response", "output_text", "content"):
        if isinstance(body.get(key), str):
            return body[key]
        if key == "content" and isinstance(body.get(key), list):
            return "".join(
                part.get("text", "") for part in body[key] if isinstance(part, dict)
            )
    return ""


def _post_chat(endpoint: str, api_key: str, payload: dict[str, Any], timeout: int) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError(str(exc)) from exc
    if response.status_code >= 400:
        raise ProviderError(f"HTTP {response.status_code}：{response.text[:240]}")
    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderError(f"返回不是 JSON：{response.text[:160]}") from exc
    content = _content_of(body)
    if not content.strip():
        raise ProviderError(f"模型没有返回内容：{json.dumps(body, ensure_ascii=False)[:200]}")
    return content


def _chat_once(config: dict[str, Any], messages: list[dict[str, str]], *, json_mode: bool) -> str:
    payload: dict[str, Any] = {
        "model": config["model"],
        "temperature": 0,
        "messages": messages,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return _post_chat(
        llm_settings.endpoint(config["base_url"]),
        config["api_key"],
        payload,
        int(config["timeout"]),
    )


def _chat(config: dict[str, Any], messages: list[dict[str, str]], *, json_mode: bool) -> str:
    """有些服务商不认 response_format，400 时去掉再试一次。"""
    try:
        return _chat_once(config, messages, json_mode=json_mode)
    except ProviderError as exc:
        if json_mode and "HTTP 4" in str(exc):
            return _chat_once(config, messages, json_mode=False)
        raise


def test_connection(
    *,
    base_url: str,
    api_key: str = "",
    model: str = "",
    timeout: int = 45,
) -> tuple[bool, str]:
    """设置页的「测试连接」。返回 (成功?, 给人看的一句话)。"""
    config = llm_settings.normalize({
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout": timeout,
        "enabled": True,
    })
    ok, reason = llm_settings.status(config)
    if not ok:
        return False, reason
    started = time.monotonic()
    try:
        content = _chat(
            config,
            [{"role": "user", "content": "只回复两个字符：OK"}],
            json_mode=False,
        )
    except ProviderError as exc:
        return False, llm_settings.friendly_error(exc)
    elapsed = time.monotonic() - started
    reply = content.strip().replace("\n", " ")[:30] or "OK"
    return True, f"连上了 · {config['model']} · {elapsed:.1f} 秒 · 回复「{reply}」"


def parse_notice(
    text: str,
    *,
    mode: str = "mock",
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    timeout: int = 45,
    reference_time: str | None = None,
    notices: list[dict[str, Any]] | None = None,
    extra: str = "",
) -> tuple[dict[str, Any], str, str | None]:
    """Return parsed data, provider label, and fallback reason (if any)."""
    if mode != "real":
        return parse_notice_mock(text), RULES_LABEL, None

    config = llm_settings.normalize({
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout": timeout,
        "enabled": True,
    })
    ok, reason = llm_settings.status(config)
    if not ok:
        return parse_notice_mock(text), f"{RULES_LABEL}（未配置）", f"大模型没启用：{reason}"

    try:
        fixed_reference_time = reference_time or datetime.now(APP_TIMEZONE).isoformat()
        input_notices = notices if notices is not None else [{"id": "N1", "text": text}]
        if not isinstance(input_notices, list) or not input_notices:
            raise ProviderError("notices 必须是非空数组")
        normalized_notices = []
        source_parts = []
        for index, notice in enumerate(input_notices, 1):
            if not isinstance(notice, dict):
                raise ProviderError("notices 每项必须是对象")
            normalized_notices.append({
                "id": str(notice.get("id") or f"N{index}"),
                "text": str(notice.get("text") or ""),
            })
            source_parts.append(str(notice.get("text") or ""))
        source_text = "\n".join(source_parts) if notices is not None else text
        user_input = {
            "reference_time": fixed_reference_time,
            "timezone": "Asia/Shanghai",
            "notices": normalized_notices,
        }
        messages = [
            {"role": "system", "content": _system_prompt(extra)},
            {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)},
        ]
        content = _chat(config, messages, json_mode=True)
        parsed = _validate_result(extract_json(content), source_text)
        return parsed, f"大模型解析 · {config['model']}", None
    except Exception as exc:  # noqa: BLE001 - 任何异常都必须回退，不能卡住流程
        friendly = llm_settings.friendly_error(exc)
        return (
            parse_notice_mock(text),
            f"{RULES_LABEL}（已回退）",
            f"大模型没走通（{friendly}），这次用本地规则。",
        )


def environment_defaults() -> dict[str, str]:
    """兼容旧调用：从环境变量取默认配置。"""
    return {
        "base_url": os.getenv("DDL_LLM_BASE_URL", ""),
        "api_key": os.getenv("DDL_LLM_API_KEY", ""),
        "model": os.getenv("DDL_LLM_MODEL", ""),
    }
