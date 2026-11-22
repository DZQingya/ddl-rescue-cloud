"""大模型配置：本地持久化 + 校验 + 人话报错。

与手机端 v1.1 的行为保持一致：
- 地址填到 /v1 就行，自动补 /chat/completions；
- 局域网地址（Ollama / LM Studio）不强制要 Key；
- 报错翻译成能看懂的一句话。

配置存在 data/llm_settings.json（可用 DDL_SETTINGS_PATH 覆盖），不跟着代码走。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "llm_settings.json"

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "base_url": "",
    "model": "",
    "api_key": "",
    "timeout": 90,
    "extra": "",
}

_TIMEOUT_RANGE = (15, 180)

# 常见服务商预设：点一下填好地址和模型，只剩 Key 要自己粘。
# 全部是 OpenAI 兼容的 /chat/completions 接口。
PRESETS: list[dict[str, str]] = [
    {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {"id": "qwen", "name": "通义千问", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    {"id": "zhipu", "name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    {"id": "kimi", "name": "Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    {"id": "openai", "name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    {"id": "siliconflow", "name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2.5-7B-Instruct"},
    {"id": "ollama", "name": "Ollama 本机", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b"},
    {"id": "lmstudio", "name": "LM Studio", "base_url": "http://127.0.0.1:1234/v1", "model": "local-model"},
]


def preset_by_id(preset_id: str) -> dict[str, str] | None:
    for preset in PRESETS:
        if preset["id"] == preset_id:
            return preset
    return None


def match_preset(config: dict[str, Any] | None) -> dict[str, str] | None:
    """当前配置命中了哪个预设（按归一后的地址比）。"""
    data = normalize(config)
    target = endpoint(data["base_url"])
    if not target:
        return None
    for preset in PRESETS:
        if endpoint(preset["base_url"]) == target:
            return preset
    return None


def settings_path() -> Path:
    override = os.environ.get("DDL_SETTINGS_PATH")
    return Path(override) if override else DEFAULT_PATH


def normalize(raw: dict[str, Any] | None) -> dict[str, Any]:
    """把任意来源的配置收敛成固定字段，坏值不抛异常。"""
    data = dict(DEFAULTS)
    if isinstance(raw, dict):
        for key in DEFAULTS:
            if key in raw and raw[key] is not None:
                data[key] = raw[key]
    data["enabled"] = bool(data["enabled"])
    data["base_url"] = str(data["base_url"] or "").strip()
    data["model"] = str(data["model"] or "").strip()
    data["api_key"] = str(data["api_key"] or "").strip()
    data["extra"] = str(data["extra"] or "").strip()
    try:
        timeout = int(data["timeout"])
    except (TypeError, ValueError):
        timeout = DEFAULTS["timeout"]
    data["timeout"] = max(_TIMEOUT_RANGE[0], min(_TIMEOUT_RANGE[1], timeout))
    return data


def load() -> dict[str, Any]:
    path = settings_path()
    raw: dict[str, Any] = {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    data = normalize(raw)
    # 没有配置文件时，允许用环境变量打底（部署到云端常用）。
    if not path.exists():
        data["base_url"] = data["base_url"] or os.environ.get("DDL_LLM_BASE_URL", "")
        data["model"] = data["model"] or os.environ.get("DDL_LLM_MODEL", "")
        data["api_key"] = data["api_key"] or os.environ.get("DDL_LLM_API_KEY", "")
    return data


def save(config: dict[str, Any]) -> dict[str, Any]:
    data = normalize(config)
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        # 云端只读磁盘等情况下不阻断使用，本次会话仍然生效。
        pass
    return data


def endpoint(url: str) -> str:
    value = re.sub(r"\s+", "", str(url or ""))
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    value = value.rstrip("/")
    if re.search(r"/completions$", value, re.I):
        return value
    if re.search(r"/v\d+$", value, re.I):
        return value + "/chat/completions"
    if re.search(r"/(api|openai)$", value, re.I):
        return value + "/v1/chat/completions"
    return value + "/v1/chat/completions"


def is_local(url: str) -> bool:
    return bool(
        re.match(
            r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[::1\])",
            str(url or ""),
            re.I,
        )
    )


def status(config: dict[str, Any] | None) -> tuple[bool, str]:
    """返回 (是否可用, 原因)。原因给用户看，不是给日志看。"""
    data = normalize(config)
    if not data["base_url"]:
        return False, "还没填接口地址"
    if not re.match(r"^https?://[^\s]+$", endpoint(data["base_url"]), re.I):
        return False, "接口地址格式不对"
    if not data["model"]:
        return False, "还没填模型名"
    if not data["api_key"] and not is_local(data["base_url"]):
        return False, "还没填 API Key"
    return True, ""


def mask(key: str) -> str:
    value = str(key or "")
    if len(value) <= 8:
        return "·" * len(value)
    return f"{value[:3]}…{value[-4:]}"


def friendly_error(message: Any) -> str:
    text = str(message or "").strip()
    if not text:
        return "调用失败，没有拿到错误信息"
    low = text.lower()
    if "401" in text or "invalid_api_key" in low or "unauthorized" in low:
        return "密钥不对或已失效（HTTP 401）"
    if "403" in text:
        return "没有权限（HTTP 403）"
    if "404" in text:
        return "接口路径不对（HTTP 404），试试只填到 /v1"
    if "429" in text:
        return "请求太频繁或额度用完了（HTTP 429）"
    if "timed out" in low or "timeout" in low or "超时" in text:
        return "请求超时，稍后再试或换个小一点的模型"
    if "connection" in low or "max retries" in low or "nameresolution" in low:
        return "连不上这个地址，检查网络或地址是否写错"
    if len(text) > 200:
        text = text[:200] + "…"
    return text
