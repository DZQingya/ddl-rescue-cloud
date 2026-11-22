"""Mock engine for DDL Rescue MVP.

This module lets the team test the product flow before wiring a real LLM API.
It uses simple keyword rules and a deterministic scheduler so the demo is stable.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


APP_TIMEZONE = timezone(timedelta(hours=8))


SAMPLE_CASES: list[dict[str, Any]] = [
    {
        "id": "clear_math",
        "label": "清晰通知",
        "scenario": "清晰",
        "text": "【数学分析】第 3 次作业：完成习题 1-5，手写拍照上传。明天23:59前提交。",
        "demo_minutes": 120,
    },
    {
        "id": "vague_english",
        "label": "模糊通知",
        "scenario": "模糊",
        "text": "英语作文下周交，具体要求课上说了，大家注意格式。",
        "demo_minutes": 120,
    },
    {
        "id": "conflict_day",
        "label": "冲突通知",
        "scenario": "冲突",
        "text": "C语言实验报告明天23:59前提交；同一天还有数学分析小测；社团招新海报也要交。",
        "demo_minutes": 30,
    },
    {
        "id": "multi_ddl",
        "label": "多DDL通知",
        "scenario": "清晰",
        "text": "【两门课作业】英语作文须于明天20:00（+08:00）前提交；数学分析习题须于明天12:00（+08:00）前提交。",
        "demo_minutes": 120,
    },
]

WORKFLOW_STEPS = [
    "识别来源",
    "抽取字段",
    "校验日期",
    "冲突检测",
    "任务拆解",
    "生成今日最小交付",
    "人工确认",
]

RESCUE_OPTIONS = [
    {
        "label": "最小可交版本",
        "description": "先完成评分点最高的 60%，其余标注 TODO，保证能提交。",
    },
    {
        "label": "申请延期 / 求助",
        "description": "给老师或助教发一条说明，附当前进度和可完成时间。",
    },
    {
        "label": "重新分配时间",
        "description": "把任务拆成 15 分钟块，优先 DDL 最近的一项。",
    },
]


_WEEKDAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_CONTEXT_WORDS = ("发的", "布置", "开课", "上课", "发布")


def _clock_of(segment: str) -> tuple[int, int] | None:
    """Extract an explicit clock such as 12点 / 中午12点 / 23:59 / 下午3点半."""
    match = re.search(
        r"(上午|中午|下午|晚上|傍晚|早上)?\s*(\d{1,2})\s*(?:[:：]\s*(\d{1,2})|[点时](?:\s*(\d{1,2})\s*分?|半)?)",
        segment,
    )
    if not match:
        return None
    hour = int(match.group(2))
    minute = int(match.group(3) or match.group(4) or (30 if "半" in match.group(0) else 0))
    period = match.group(1) or ""
    if period in ("下午", "晚上", "傍晚") and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _weekday_date(today: datetime, weeks: int, target: int) -> datetime:
    """Monday-based weekday date: weeks=0 本周, 1 下周, 2 下下周."""
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=weeks * 7 + target)


def _extract_time(text: str) -> dict[str, Any]:
    """Date semantics: explicit / relative / window / past / contradiction."""
    now = datetime.now(APP_TIMEZONE)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    info: dict[str, Any] = {
        "deadline": None,
        "source": "原文未给出明确日期",
        "basis": "none",
        "past": False,
        "invalid": False,
        "conflict": False,
        "candidates": [],
        "window": None,
    }

    explicit: list[dict[str, Any]] = []
    invalid_raw = ""
    for match in re.finditer(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日", text):
        year = int(match.group(1)) if match.group(1) else now.year
        month, day = int(match.group(2)), int(match.group(3))
        suffix = text[match.end(): match.end() + 16]
        clock = _clock_of(suffix)
        hour, minute = clock or (23, 59)
        try:
            value = datetime(year, month, day, hour, minute, tzinfo=APP_TIMEZONE)
        except ValueError:
            invalid_raw = match.group(0)
            continue
        explicit.append(
            {
                "value": value,
                "raw": match.group(0),
                "context": any(word in suffix[:10] for word in _CONTEXT_WORDS),
                "expired": value < now,
            }
        )

    usable = [item for item in explicit if not item["context"] and not item["expired"]]
    expired = [item for item in explicit if not item["context"] and item["expired"]]

    if usable:
        chosen = usable[0]
        info.update(deadline=chosen["value"], source=chosen["raw"], basis="explicit")
        info["candidates"] = [item["value"].strftime("%Y-%m-%d") for item in usable[1:]]
        return info

    relative = re.search(r"(今天|明天|后天)", text)
    if relative:
        offset = {"今天": 0, "明天": 1, "后天": 2}[relative.group(1)]
        clock = _clock_of(text[relative.end(): relative.end() + 14])
        hour, minute = clock or (23, 59)
        value = (today + timedelta(days=offset)).replace(hour=hour, minute=minute)
        info.update(deadline=value, source=relative.group(0), basis="relative")
        return info

    weekday = re.search(r"(本|这|下下|下)\s*周\s*([一二三四五六日天])", text)
    if weekday:
        weeks = {"本": 0, "这": 0, "下": 1, "下下": 2}[weekday.group(1)]
        clock = _clock_of(text[weekday.end(): weekday.end() + 14])
        hour, minute = clock or (23, 59)
        target = _WEEKDAY_INDEX[weekday.group(2)]
        value = _weekday_date(today, weeks, target).replace(hour=hour, minute=minute)
        info.update(deadline=value, source=weekday.group(0), basis="relative")
        if "本周" in text and "下周" in text:
            info["conflict"] = True
            info["candidates"] = [
                _weekday_date(today, 0, 4).strftime("%Y-%m-%d"),
                _weekday_date(today, 1, 4).strftime("%Y-%m-%d"),
            ]
        elif weeks == 1:
            info["candidates"] = [
                _weekday_date(today, 0, target).strftime("%Y-%m-%d"),
                value.strftime("%Y-%m-%d"),
            ]
        return info

    window = re.search(r"(这|本|下)\s*周(?:内|之内|里)?", text)
    if window:
        weeks = {"这": 0, "本": 0, "下": 1}[window.group(1)]
        start = _weekday_date(today, weeks, 0)
        end = start + timedelta(days=6)
        info.update(
            source=window.group(0),
            basis="window",
            window=(start.replace(hour=0, minute=0), end.replace(hour=23, minute=59)),
        )
        return info

    if "月底" in text:
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
        info.update(
            source="月底",
            basis="window",
            window=(today, end.replace(hour=23, minute=59)),
        )
        return info

    if expired:
        info.update(source=f"原文日期已过期（{expired[0]['raw']}）", past=True)
        return info
    if invalid_raw:
        info.update(source=f"无法识别的日期（{invalid_raw}）", invalid=True)
    return info


def _find_deadline(text: str) -> tuple[datetime | None, str]:
    """Backward-compatible wrapper around _extract_time."""
    info = _extract_time(text)
    return info["deadline"], info["source"]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _title_covered(candidate: str, item_titles: list[str]) -> bool:
    """判断通用交付物抽取是否已被某个 DDL 标题覆盖。"""
    def norm(value: str) -> str:
        value = re.sub(r"\s+", "", value)
        value = value.removeprefix("完成")
        return value

    cand = norm(candidate)
    return any(
        cand in norm(title) or norm(title) in cand or (cand and cand[-1:] in norm(title))
        for title in item_titles
    )


def _extract_deliverables(text: str, subject: str) -> list[str]:
    """Only items with literal evidence in the notice; no template completion."""
    items: list[str] = []
    exercise = re.search(r"习题\s*([0-9]+(?:\s*[-–—~至]\s*[0-9]+)?)", text)
    if exercise:
        span = re.sub(r"\s+", "", exercise.group(1))
        items.append("完成习题 " + span)
    essay = re.search(r"(\d+)\s*字\s*(?:的)?\s*(?:英语)?作文", text)
    if essay:
        items.append(f"{essay.group(1)} 字作文")
    elif "作文" in text:
        items.append("英语作文" if "英语" in text else "作文")
    report = re.search(r"实验[一二三四五六七八九十\d]*\s*报告", text)
    if report:
        name = re.sub(r"\s+", "", report.group(0))
        items.append(name if not subject or subject in name else subject + name)
    if "海报" in text:
        items.append("社团招新海报" if "社团" in text else "海报")
    if "PPT" in text or "汇报" in text or "展示" in text:
        items.append("课程展示 PPT")
    if "小测" in text:
        items.append("课程小测")
    if "题目" in text and not items:
        items.append("完成课上发的题目")
    if not items:
        items.append("完成通知要求的作业")
    return _unique(items)


def _extract_materials(text: str) -> list[str]:
    items: list[str] = []
    if "实验数据" in text:
        items.append("实验数据")
    if "代码" in text:
        items.append("代码文件")
    if "教材" in text:
        items.append("教材")
    return _unique(items)


def _deadline_record(value: datetime, source: str, basis: str) -> dict[str, Any]:
    """Scheduler/adapter 共用的单条截止时间结构。"""
    return {
        "raw": source,
        "normalized": value.isoformat(),
        "confidence": 0.90 if basis == "explicit" else 0.80,
        "source_span": source,
    }


def _deadline_anchor_start(segment: str, info: dict[str, Any]) -> int | None:
    """定位该片段中实际用于截止时间的那一个日期/相对时间。"""
    source = str(info.get("source") or "")
    if source:
        index = segment.find(source)
        if index >= 0:
            return index
    if info.get("basis") == "explicit":
        match = re.search(r"(?:\d{4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*日", segment)
        return match.start() if match else None
    relative = re.search(r"(今天|明天|后天|(?:本|这|下下|下)\s*周\s*[一二三四五六日天])", segment)
    return relative.start() if relative else None


def _clean_ddl_title(prefix: str, index: int) -> str:
    """从截止时间左侧提取该 DDL 对应的交付物名称。"""
    value = prefix.strip()
    value = re.sub(r"^【[^】]*】\s*", "", value)
    value = re.sub(r"^(?:请|另外|同时|并且|且|需要)\s*", "", value)
    value = re.sub(r"[，,：:\s]*(?:须|需|应|必须|要求|请)\s*(?:于|在)?\s*$", "", value)
    value = re.sub(r"[，,：:\s]*(?:于|在|截止到|截止时间[：:]?)\s*$", "", value)
    value = value.strip(" \t\r\n，,。；;：:")
    if "：" in value or ":" in value:
        value = re.split(r"[：:]", value, maxsplit=1)[0].strip()
    if len(value) > 48 or "\n" in value:
        value = re.split(r"[，,。；;：:]", value)[-1].strip()
    return value or f"交付物 {index}"


def _extract_ddl_task_titles(segment: str, title: str) -> list[str]:
    """优先抽取“，需……”之后的任务；否则给一个可执行的默认任务。"""
    requirement = re.search(r"[，,]\s*需(?:要)?\s*(.+?)(?=[。；;]|$)", segment)
    if requirement is None:
        requirement = re.search(r"(?:任务|要求)[为是：:]\s*(.+?)(?=[。；;]|$)", segment)
    if requirement is None:
        return [f"完成{title}"]

    raw = requirement.group(1).strip()
    raw = re.sub(r"[，,]\s*(?:三个|以上|请分别|分别|所有).*$", "", raw)
    parts = re.split(r"\s*(?:以及|并且|(?<!合)并|和|、)\s*", raw)
    tasks: list[str] = []
    for part in parts:
        item = part.strip(" \t\r\n，,。；;：:")
        if title.startswith("实验报告") and item.startswith("将报告"):
            item = "将实验报告" + item[len("将报告"):]
        if title == "实验代码" and item and not item.startswith(
            ("完成", "撰写", "制作", "检查", "将", "导出", "整理", "提交")
        ):
            item = "完成" + item
        if item:
            tasks.append(item)
    return _unique(tasks) or [f"完成{title}"]


def _task_tag_for_title(title: str) -> str:
    if "英语" in title:
        return "英语"
    if any(word in title for word in ("数学", "习题", "小测")):
        return "数学"
    if any(word in title for word in ("实验", "代码")):
        return "实验"
    if any(word in title for word in ("PPT", "展示")):
        return "展示"
    if "海报" in title:
        return "社团"
    return title


def _task_minutes_for_title(title: str) -> int:
    if any(word in title for word in ("检查", "导出")):
        return 15
    if "自测" in title:
        return 20
    if any(word in title for word in ("撰写", "PPT", "制作")):
        return 35
    return 30


def _make_multi_ddl_task(
    title: str,
    ddl_id: str,
    task_index: int,
    deadline: dict[str, Any],
    tag: str,
) -> dict[str, Any]:
    minutes = _task_minutes_for_title(title)
    warm_start = f"打开与「{title}」相关的要求或文件，先完成一个最小动作。"
    done_definition = f"{title}已有可见成果，并能对照通知要求确认完成。"
    return {
        "id": f"{ddl_id}_T{task_index}",
        "title": title,
        "minutes": minutes,
        "estimate_min": minutes,
        "warm_start": warm_start,
        "done_definition": done_definition,
        "levels": _default_levels(title, minutes, done_definition),
        "tag": tag,
        "ddl_id": ddl_id,
        "deadline": dict(deadline),
        "done": False,
    }


def _extract_multi_ddl_items(text: str) -> list[dict[str, Any]]:
    """从分号分隔的声明中抽取两个及以上可确认的 DDL。

    这是 MVP 的确定性规则：不猜未写出的日期；同一片段有冲突或歧义时跳过，
    最终少于两个有效 DDL 就退回原有单 DDL 逻辑。
    """
    clauses = [clause.strip() for clause in re.split(r"[；;。]+", text) if clause.strip()]
    items: list[dict[str, Any]] = []
    for clause in clauses:
        info = _extract_time(clause)
        deadline = info.get("deadline")
        if not deadline or info.get("conflict") or info.get("basis") not in ("explicit", "relative"):
            continue
        anchor = _deadline_anchor_start(clause, info)
        if anchor is None:
            continue
        index = len(items) + 1
        title = _clean_ddl_title(clause[:anchor], index)
        ddl_id = f"DDL{index}"
        deadline_data = _deadline_record(deadline, str(info["source"]), str(info["basis"]))
        task_titles = _extract_ddl_task_titles(clause, title)
        tasks = [
            _make_multi_ddl_task(
                task_title,
                ddl_id,
                task_index,
                deadline_data,
                _task_tag_for_title(title),
            )
            for task_index, task_title in enumerate(task_titles, start=1)
        ]
        items.append(
            {
                "id": ddl_id,
                "title": title,
                "deadline": deadline_data,
                "deadline_iso": deadline.isoformat(),
                "deadline_source": str(info["source"]),
                "deadline_basis": str(info["basis"]),
                "deliverables": [title],
                "materials": _extract_materials(clause),
                "risks": [],
                "tasks": tasks,
                "confidence": deadline_data["confidence"],
                "source_span": clause,
            }
        )
    return items if len(items) >= 2 else []


def parse_notice(text: str) -> dict[str, Any]:
    """Rule-based extraction with date semantics, ambiguity flags and a gate."""
    text = text.strip()
    info = _extract_time(text)
    multi_items = _extract_multi_ddl_items(text)
    multi_ddl = len(multi_items) >= 2

    if multi_ddl:
        earliest_item = min(
            multi_items,
            key=lambda item: datetime.fromisoformat(item["deadline_iso"]),
        )
        deadline = datetime.fromisoformat(earliest_item["deadline_iso"])
        deadline_source = earliest_item["deadline_source"]
        basis = earliest_item["deadline_basis"]
    else:
        deadline = info["deadline"]
        deadline_source = info["source"]
        basis = info["basis"]

    subject_match = re.search(r"【(.+?)】", text)
    subject = subject_match.group(1).strip() if subject_match else ""
    title = subject or (text[:18] + ("…" if len(text) > 18 else ""))

    extracted_deliverables = _extract_deliverables(text, subject)
    extra_deliverables: list[str] = []
    if multi_ddl:
        item_titles = [str(item["title"]) for item in multi_items]
        extra_deliverables = [
            name for name in extracted_deliverables if not _title_covered(name, item_titles)
        ]
        deliverables = _unique(item_titles + extra_deliverables)
    else:
        deliverables = extracted_deliverables
    materials = _extract_materials(text)

    risks: list[dict[str, str]] = []
    blocking = 0
    if deadline is None:
        if info["past"]:
            message = "原文日期已过期，不能当作未来的截止时间；需要确认新的截止时间。"
        elif info["invalid"]:
            message = "原文日期无法识别（可能不是有效日期），需要确认具体截止时间。"
        else:
            message = "原文没有明确日期，需要确认具体截止时间。"
        risks.append({"type": "ambiguity", "message": message, "severity": "high"})
        blocking += 1
    if info["conflict"]:
        risks.append(
            {
                "type": "conflict",
                "message": "「本周」与「下周」的时间口径互相矛盾，需确认按哪一周执行。",
                "severity": "high",
            }
        )
        blocking += 1
    elif info["candidates"] and not multi_ddl:
        risks.append(
            {
                "type": "ambiguity",
                "message": "相对时间存在两种口语理解（本周/下周），已按自然周取值，需要确认。",
                "severity": "medium",
            }
        )
    if "另行通知" in text:
        risks.append(
            {
                "type": "ambiguity",
                "message": "有要求「另行通知」，当前无法确定具体时间/方式/尺寸，需要追问。",
                "severity": "high",
            }
        )
        blocking += 1
    if any(word in text for word in ("格式要求不明", "格式未说明", "注意格式", "格式要求")):
        risks.append(
            {
                "type": "ambiguity",
                "message": "格式/具体要求未给出，提交前需要向老师或课代表确认。",
                "severity": "high",
            }
        )
        blocking += 1
    if "尽快" in text:
        risks.append(
            {
                "type": "ambiguity",
                "message": "「尽快」是模糊时限，建议尽快确认一个具体日期。",
                "severity": "medium",
            }
        )
    deadline_values = [
        datetime.fromisoformat(item["deadline_iso"]) for item in multi_items
    ]
    same_deadline_collision = multi_ddl and len(set(deadline_values)) < len(deadline_values)
    has_unbound_deliverable = multi_ddl and bool(extra_deliverables)
    if extra_deliverables:
        risks.append(
            {
                "type": "conflict",
                "message": (
                    "同一天还存在未绑定独立截止时间的交付物："
                    + "、".join(extra_deliverables)
                    + "；需要确认它们是否与现有 DDL 共用截止时间。"
                ),
                "severity": "high",
            }
        )
        blocking += 1
    if (not multi_ddl and (len(deliverables) > 1 or "同一天" in text)) or same_deadline_collision:
        risks.append(
            {
                "type": "conflict",
                "message": (
                    "多个 DDL 落在同一截止时刻，需要确认是否能同时完成。"
                    if same_deadline_collision
                    else "同一时间段存在多个交付物，可能发生冲突。"
                ),
                "severity": "high",
            }
        )
        blocking += 1

    if deadline is None:
        confidence = 0.40 if (info["past"] or info["invalid"]) else 0.55
        scenario = "模糊"
    elif multi_ddl:
        confidence = 0.90 if basis == "explicit" else 0.88
        scenario = "冲突" if (info["conflict"] or same_deadline_collision or has_unbound_deliverable) else "清晰"
    else:
        confidence = 0.90 if basis == "explicit" else 0.55
        scenario = "冲突" if (info["conflict"] or len(deliverables) > 1) else "清晰"
    if blocking:
        confidence = min(confidence, 0.60)

    schedule_ready = (
        deadline is not None
        and basis in ("explicit", "relative")
        and not info["conflict"]
        and not same_deadline_collision
    )

    return {
        "title": title,
        "raw_text": text,
        "scenario": scenario,
        "deadline": deadline.strftime("%Y-%m-%d %H:%M") if deadline else "待确认",
        "deadline_iso": deadline.isoformat() if deadline else None,
        "deadline_source": deadline_source,
        "deadline_basis": basis,
        "deadline_candidates": (
            [item["deadline_iso"] for item in multi_items if item["deadline_iso"] != deadline.isoformat()]
            if deadline is not None and multi_ddl
            else info["candidates"]
        ),
        "deadline_window": (
            {"start": info["window"][0].isoformat(), "end": info["window"][1].isoformat()}
            if info["window"]
            else None
        ),
        "schedule_ready": schedule_ready,
        "deliverables": _unique(deliverables),
        "materials": _unique(materials),
        "risks": risks,
        "confidence": confidence,
        "ddl_count": len(multi_items) if multi_ddl else (1 if deadline is not None else 0),
        "ddl_items": multi_items if multi_ddl else [],
        "source_spans": _unique(
            [deadline_source, text[:90]]
            + [str(item.get("deadline_source") or "") for item in multi_items]
        ),
        "workflow": WORKFLOW_STEPS,
    }


def _default_levels(title: str, minutes: int, done_definition: str) -> dict[str, dict[str, Any]]:
    """Create a three-step encouragement ladder for a task."""
    return {
        "minimum": {
            "label": "保底",
            "deliverable": title,
            "minutes": minutes,
            "done_definition": done_definition,
        },
        "standard": {
            "label": "进阶",
            "deliverable": f"{title}，并完成一次自查",
            "minutes": minutes + 5,
            "done_definition": f"{done_definition}，并检查是否符合要求。",
        },
        "stretch": {
            "label": "挑战",
            "deliverable": f"{title}，再向前多做一步",
            "minutes": minutes + 15,
            "done_definition": f"{done_definition}，并留下一个额外的延伸成果。",
        },
    }


def _add_task(
    tasks: list[dict[str, Any]],
    title: str,
    minutes: int,
    warm_start: str,
    done_definition: str,
    tag: str,
    levels: dict[str, dict[str, Any]] | None = None,
) -> None:
    tasks.append(
        {
            "id": f"T{len(tasks) + 1}",
            "title": title,
            "minutes": minutes,
            "warm_start": warm_start,
            "done_definition": done_definition,
            "levels": levels or _default_levels(title, minutes, done_definition),
            "tag": tag,
            "done": False,
        }
    )


def _blocked_plan(parsed: dict[str, Any]) -> dict[str, Any]:
    """No confirmed deadline -> no schedule.

    Product rule (P0-1): 没有截止时间就不排期，只给一个「先确认截止时间」的动作，
    不再回退到 7 天兜底排期。
    """
    return {
        "tasks": [],
        "plan_days": [],
        "today_tasks": [],
        "today_levels": {
            "minimum": {
                "label": "保底",
                "deliverable": "问清截止时间",
                "minutes": 5,
                "done_definition": "已向老师/课代表发出确认消息，并记下回复的截止时间。",
            },
            "standard": {
                "label": "进阶",
                "deliverable": "问清截止时间并写进日历",
                "minutes": 10,
                "done_definition": "截止时间已确认，并创建了一条日历提醒。",
            },
            "stretch": {
                "label": "挑战",
                "deliverable": "顺带确认提交方式与格式",
                "minutes": 15,
                "done_definition": "截止时间、提交方式、格式要求三项都已确认。",
            },
        },
        "today_deliverable": "先确认截止时间",
        "today_warm_start": "打开通知原文，找到提到时间的那一句。",
        "today_done_definition": "已向老师/课代表发出确认消息，并记下回复的截止时间。",
        "today_first_step": "先确认截止时间",
        "today_task_title": "先确认截止时间",
        "today_minutes": 5,
        "required_minutes": 0,
        "capacity_minutes": 0,
        "feasible": False,
        "conflict_message": "截止时间未确认，暂不排期。先问清楚截止时间，再生成计划。",
        "scheduling_engine": "blocked",
        "rescue_options": RESCUE_OPTIONS,
        "progress_pct": 0,
    }


def _flatten_ddl_item_tasks(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """把多 DDL 的嵌套任务铺平成旧 UI 可消费的任务数组。"""
    flattened: list[dict[str, Any]] = []
    for item in parsed.get("ddl_items") or []:
        if not isinstance(item, dict):
            continue
        ddl_id = str(item.get("id") or "DDL")
        deadline = item.get("deadline")
        if not isinstance(deadline, dict):
            deadline = {
                "raw": item.get("deadline_source") or item.get("deadline_iso") or "",
                "normalized": item.get("deadline_iso"),
                "confidence": item.get("confidence", 0.8),
                "source_span": item.get("deadline_source") or item.get("deadline_iso") or "",
            }
        for raw_task in item.get("tasks") or []:
            if not isinstance(raw_task, dict):
                continue
            task = dict(raw_task)
            levels = task.get("levels") if isinstance(task.get("levels"), dict) else {}
            minimum = levels.get("minimum") if isinstance(levels.get("minimum"), dict) else {}
            minutes = int(task.get("minutes") or task.get("estimate_min") or minimum.get("minutes") or 30)
            title = str(task.get("title") or "任务")
            done_definition = str(task.get("done_definition") or f"{title}已有可见成果。")
            task.setdefault("levels", _default_levels(title, minutes, done_definition))
            task.setdefault("warm_start", f"打开与「{title}」相关的要求或文件。")
            task.setdefault("done_definition", done_definition)
            task.setdefault("tag", str(item.get("title") or "多 DDL"))
            task.setdefault("minutes", minutes)
            task.setdefault("done", False)
            task["ddl_id"] = ddl_id
            task["deadline"] = dict(deadline)
            flattened.append(task)
    flattened.sort(
        key=lambda task: datetime.fromisoformat(str(task["deadline"]["normalized"]))
    )
    return flattened


def build_plan(parsed: dict[str, Any], available_minutes: int = 120, days: int = 7) -> dict[str, Any]:
    """Deterministic planner: meaningful work block + tiny warm start.

    Key product rule:
    - ``warm_start`` is a 2-5 minute action and is NOT the "today first step".
    - ``title`` is the smallest meaningful deliverable for today, usually 20-45 min.
    """
    if not parsed.get("deadline_iso") or parsed.get("schedule_ready") is False:
        # P0-1：没有确认的截止时间（或时间口径自相矛盾）就没有可执行的排期。
        return _blocked_plan(parsed)

    multi_tasks = _flatten_ddl_item_tasks(parsed)
    text = "" if multi_tasks else parsed.get("raw_text", "")
    tasks: list[dict[str, Any]] = list(multi_tasks)

    if any(word in text for word in ["数学", "习题", "小测", "高数", "数分"]):
        _add_task(
            tasks,
            "完成第 1 题的完整过程",
            30,
            "打开作业 PDF，找到第 1 题，圈出已知条件和所求。",
            "第 1 题有完整步骤和最终答案，能拍照上传。",
            "数学",
            levels={
                "minimum": {"label": "保底", "deliverable": "完成第 1 题的完整过程", "minutes": 30, "done_definition": "第 1 题有完整步骤和最终答案，能拍照上传。"},
                "standard": {"label": "进阶", "deliverable": "完成第 1 题并检查计算", "minutes": 35, "done_definition": "第 1 题步骤完整，计算检查过，能拍照上传。"},
                "stretch": {"label": "挑战", "deliverable": "完成第 1 题，并尝试第 2 题第一问", "minutes": 45, "done_definition": "第 1 题完整，第 2 题写出第一步和思路。"},
            },
        )
        _add_task(
            tasks,
            "完成第 2–3 题",
            35,
            "先看第 2 题，写出已知条件和目标。",
            "第 2、3 题各有完整步骤，没有跳步。",
            "数学",
        )
        _add_task(
            tasks,
            "完成剩余题目",
            35,
            "翻到最后一题，先写第一行推导。",
            "所有题目都有解答，没有空题。",
            "数学",
        )
        _add_task(
            tasks,
            "检查并拍照上传",
            15,
            "打开手机相机，先拍第 1 页。",
            "按顺序拍照、命名正确并完成上传。",
            "数学",
        )
    if any(word in text for word in ["英语", "作文"]):
        _add_task(
            tasks,
            "写完作文第一段",
            25,
            "看要求，写下 3 句中文提纲。",
            "第一段 150–200 字，有明确主题句。",
            "英语",
            levels={
                "minimum": {"label": "保底", "deliverable": "写完作文第一段", "minutes": 25, "done_definition": "第一段 150–200 字，有明确主题句。"},
                "standard": {"label": "进阶", "deliverable": "写完第一段并检查语法", "minutes": 30, "done_definition": "第一段有主题句，语法和拼写检查过。"},
                "stretch": {"label": "挑战", "deliverable": "写完第一段并列出主体提纲", "minutes": 40, "done_definition": "第一段完成，主体两段提纲清楚。"},
            },
        )
        _add_task(
            tasks,
            "写完作文主体",
            40,
            "打开第一段，先写一句过渡。",
            "主体两段完成，论点清楚，有例子支撑。",
            "英语",
        )
        _add_task(
            tasks,
            "修改并提交",
            25,
            "先检查字数是否达标。",
            "字数、格式、引用检查完，已提交。",
            "英语",
        )
    if any(word in text for word in ["C语言", "实验报告", "代码", "实验"]):
        _add_task(
            tasks,
            "整理实验数据和结果表",
            30,
            "打开实验数据，先列出 3 个结果表。",
            "3 个结果表和 1 个待解释的问题整理完成。",
            "实验",
            levels={
                "minimum": {"label": "保底", "deliverable": "整理实验数据和结果表", "minutes": 30, "done_definition": "3 个结果表和 1 个待解释的问题整理完成。"},
                "standard": {"label": "进阶", "deliverable": "整理数据并完成 1 张结果图", "minutes": 40, "done_definition": "结果表整理完成，并有 1 张能说明问题的图。"},
                "stretch": {"label": "挑战", "deliverable": "整理数据、完成图表并写出结果解释", "minutes": 45, "done_definition": "结果表、图表和一句结果解释都完成。"},
            },
        )
        _add_task(
            tasks,
            "写完实验方法",
            35,
            "打开报告模板，先写实验目的。",
            "方法部分完整，别人能按步骤复现。",
            "实验",
        )
        _add_task(
            tasks,
            "写完结果与结论",
            35,
            "先写结果 1 的一句话结论。",
            "结果与结论对应，图表编号正确。",
            "实验",
        )
        _add_task(
            tasks,
            "检查并导出 PDF",
            15,
            "打开模板，先检查标题和页码。",
            "格式正确，PDF 已导出并命名。",
            "实验",
        )
    if any(word in text for word in ["海报", "社团"]):
        _add_task(
            tasks,
            "完成海报主视觉",
            30,
            "打开社团相册，先选 3 张可用素材。",
            "主视觉和主标题完成，能看出活动主题。",
            "社团",
            levels={
                "minimum": {"label": "保底", "deliverable": "完成海报主视觉", "minutes": 30, "done_definition": "主视觉和主标题完成，能看出活动主题。"},
                "standard": {"label": "进阶", "deliverable": "完成主视觉和主文案", "minutes": 35, "done_definition": "主视觉、主标题和活动卖点都完成。"},
                "stretch": {"label": "挑战", "deliverable": "完成主视觉、文案和初版排版", "minutes": 45, "done_definition": "主视觉、文案和初版排版都能直接预览。"},
            },
        )
        _add_task(
            tasks,
            "完成文案和排版",
            30,
            "先写一句主标题和 3 个活动卖点。",
            "文案完整，尺寸和留白符合要求。",
            "社团",
        )
        _add_task(
            tasks,
            "导出并提交",
            15,
            "先检查海报尺寸。",
            "PNG/JPG 已导出，按指定方式提交。",
            "社团",
        )
    if any(word in text for word in ["展示", "汇报", "PPT", "pre"]):
        _add_task(
            tasks,
            "完成 5 页 PPT 初稿",
            35,
            "先写 5 个页面标题，不找配图。",
            "5 页都有标题和要点，逻辑能串起来。",
            "展示",
            levels={
                "minimum": {"label": "保底", "deliverable": "完成 5 页 PPT 初稿", "minutes": 35, "done_definition": "5 页都有标题和要点，逻辑能串起来。"},
                "standard": {"label": "进阶", "deliverable": "完成 5 页并补 1 个图表", "minutes": 40, "done_definition": "5 页结构完整，至少 1 页有图表支撑。"},
                "stretch": {"label": "挑战", "deliverable": "完成 5 页、图表和讲稿", "minutes": 50, "done_definition": "5 页 PPT、图表和逐页讲稿都完成。"},
            },
        )
        _add_task(
            tasks,
            "补充图表和案例",
            35,
            "先找 1 张能支撑观点的图。",
            "每页至少有 1 个支撑材料。",
            "展示",
        )
        _add_task(
            tasks,
            "演练并提交",
            20,
            "计时讲第一页。",
            "5 分钟内讲完，文件已上传。",
            "展示",
        )

    if not tasks:
        _add_task(
            tasks,
            "完成最小可交版本的第一部分",
            30,
            "打开通知，圈出评分点最高的要求。",
            "第一部分达到可提交状态。",
            "通用",
            levels={
                "minimum": {"label": "保底", "deliverable": "完成最小可交版本的第一部分", "minutes": 30, "done_definition": "第一部分达到可提交状态。"},
                "standard": {"label": "进阶", "deliverable": "完成第一部分并对照要求检查", "minutes": 35, "done_definition": "第一部分完整，并逐项对照了要求。"},
                "stretch": {"label": "挑战", "deliverable": "完成第一部分并开始第二部分", "minutes": 45, "done_definition": "第一部分可提交，第二部分已写出开头。"},
            },
        )
        _add_task(
            tasks,
            "完成剩余部分",
            35,
            "先做第二部分的第一小问。",
            "通知里的所有要求都有对应内容。",
            "通用",
        )
        _add_task(
            tasks,
            "检查并提交",
            15,
            "打开提交页面。",
            "逐项检查后提交成功。",
            "通用",
        )

    scheduling_engine = "fallback"
    scheduled = None
    try:
        from team_scheduler.adapter import schedule_plan

        scheduler_tasks = [] if multi_tasks else tasks
        scheduled = schedule_plan(parsed, scheduler_tasks, available_minutes=available_minutes, days=days)
    except Exception:
        scheduled = None

    if scheduled is not None:
        plan_days = scheduled["plan_days"]
        required = scheduled["required_minutes"]
        capacity = scheduled["capacity_minutes"]
        feasible = scheduled["feasible"]
        parser_conflicts = [
            str(risk.get("message") or "")
            for risk in parsed.get("risks", [])
            if isinstance(risk, dict) and risk.get("type") == "conflict"
        ]
        conflict_message = "；".join(
            _unique([str(scheduled.get("conflict_message") or "")] + parser_conflicts)
        ).strip("；")
        scheduling_engine = "team_scheduler"
    else:
        capacity = available_minutes * days
        required = sum(task["minutes"] for task in tasks)
        feasible = required <= capacity

        remaining = list(tasks)
        plan_days = []
        for day_index in range(days):
            day_tasks: list[dict[str, Any]] = []
            used = 0
            while remaining and used + remaining[0]["minutes"] <= available_minutes:
                task = remaining.pop(0)
                day_tasks.append(task)
                used += task["minutes"]
            if not day_tasks and remaining:
                task = remaining.pop(0)
                day_tasks.append(task)
                used = task["minutes"]
            plan_days.append(
                {
                    "day": "今天" if day_index == 0 else f"第 {day_index + 1} 天",
                    "tasks": day_tasks,
                    "minutes": used,
                }
            )
        conflict_message = ""
        if not feasible:
            conflict_message = (
                f"本周容量不足：任务约需 {required} 分钟，可用只有 {capacity} 分钟。"
                "不要硬排，建议砍范围、拆分任务或申请延期。"
            )

    today_tasks = plan_days[0]["tasks"] if plan_days else []
    scheduled_ids = {
        str(task.get("id", ""))
        for day in plan_days
        for task in day.get("tasks", [])
    }
    unscheduled_tasks: list[dict[str, Any]] = []
    for task in tasks:
        if str(task.get("id", "")) in scheduled_ids:
            continue
        deferred = dict(task)
        deferred["replan_status"] = "deferred"
        deferred["deferred_reason"] = "当前计划窗口内没有足够容量，需延期或砍范围。"
        unscheduled_tasks.append(deferred)
    first_task = today_tasks[0] if today_tasks else tasks[0]
    # 跨通知聚合可能把不同来源的任务拼在一起；旧任务的 levels/warm_start
    # 字段可能不完整，展示层需要补齐后再读取。
    first_task.setdefault(
        "levels",
        _default_levels(
            str(first_task.get("title") or "任务"),
            int(first_task.get("minutes", first_task.get("estimate_min", 30)) or 30),
            str(first_task.get("done_definition") or "完成这个任务块。"),
        ),
    )
    first_task.setdefault("warm_start", str(first_task.get("first_step") or "打开任务要求。"))
    first_task.setdefault("done_definition", "完成这个任务块。")
    first_task.setdefault("minutes", int(first_task.get("estimate_min", 30) or 30))

    return {
        "tasks": tasks,
        "plan_days": plan_days,
        "unscheduled_tasks": unscheduled_tasks,
        "deferred_message": (
            "有任务无法放入当前计划窗口，已标记为延期/砍范围："
            + "、".join(str(task.get("title", "任务")) for task in unscheduled_tasks)
            if unscheduled_tasks
            else ""
        ),
        "today_tasks": today_tasks,
        "today_levels": first_task["levels"],
        "today_deliverable": first_task["title"],
        "today_warm_start": first_task["warm_start"],
        "today_done_definition": first_task["done_definition"],
        "today_first_step": first_task["title"],
        "today_task_title": first_task["title"],
        "today_minutes": first_task["minutes"],
        "required_minutes": required,
        "capacity_minutes": capacity,
        "feasible": feasible,
        "conflict_message": conflict_message,
        "scheduling_engine": scheduling_engine,
        "rescue_options": RESCUE_OPTIONS,
        "progress_pct": 0,
    }


def _escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def generate_ics(parsed: dict[str, Any]) -> str:
    """Generate a minimal .ics file for an actionable deadline."""
    deadline_iso = parsed.get("deadline_iso")
    if not deadline_iso or parsed.get("schedule_ready") is False:
        return ""
    deadline = datetime.fromisoformat(deadline_iso)
    end = deadline + timedelta(minutes=30)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = _escape_ics(f"DDL: {parsed.get('title', '作业')}")
    description = _escape_ics(parsed.get("raw_text", ""))
    return "\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//DDL Rescue//CN",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@ddl-rescue.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{deadline.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
