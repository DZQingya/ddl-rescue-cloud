"""电脑端 v0.9（同步手机端 v1.2）回归：大模型接入、服务商预设、日历选时、手动确认截止时间。

跑法（项目根目录）：
    python tests/test_sync_v09.py
会自动起一个本地假模型服务（tools/mock_llm.py，端口 8802），不会联网。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
sys.path.insert(0, str(WORK))

MOCK_PORT = 8802
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"

checks: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, extra: str = "") -> None:
    checks.append((name, bool(cond), extra))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if extra else ""))


def start_mock() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "mock_llm.py"), str(MOCK_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(MOCK_URL, timeout=1)
        except Exception:
            time.sleep(0.3)
            continue
        return proc
    return proc


def main() -> int:
    mock = start_mock()
    tmpdir = Path(tempfile.mkdtemp(prefix="ddl-sync-"))
    os.environ["DDL_SETTINGS_PATH"] = str(tmpdir / "llm_settings.json")

    try:
        import deadline_tools
        import llm_settings
        import model_provider as provider
        from mock_engine import build_plan

        # ---------- 1. 配置工具 ----------
        ok("地址补全 /v1", llm_settings.endpoint("https://api.deepseek.com") == "https://api.deepseek.com/v1/chat/completions")
        ok("已有 /v1 不重复", llm_settings.endpoint("https://api.deepseek.com/v1").endswith("/v1/chat/completions"))
        ok("已写全不再加", llm_settings.endpoint("http://x/v1/chat/completions").count("/chat/completions") == 1)
        ok("智谱 v4 路径", llm_settings.endpoint("https://open.bigmodel.cn/api/paas/v4").endswith("/paas/v4/chat/completions"))
        ok("识别局域网", llm_settings.is_local("http://192.168.1.5:11434/v1") and not llm_settings.is_local("https://api.openai.com/v1"))
        ok("云端必须填 Key", llm_settings.status({"base_url": "https://api.deepseek.com/v1", "model": "x"})[0] is False)
        ok("局域网免 Key", llm_settings.status({"base_url": "http://127.0.0.1:11434/v1", "model": "x"})[0] is True)
        ok("报错翻译 401", "密钥" in llm_settings.friendly_error("HTTP 401: invalid_api_key"))

        saved = llm_settings.save({"enabled": True, "base_url": MOCK_URL, "model": "mock-model", "api_key": "sk-mock", "timeout": 20})
        ok("配置落盘", (tmpdir / "llm_settings.json").exists() and saved["timeout"] == 20)
        ok("读回一致", llm_settings.load()["model"] == "mock-model")
        ok("超时被夹住", llm_settings.normalize({"timeout": 9999})["timeout"] == 180)

        # ---------- 2. 预设 ----------
        ok("预设数量", len(llm_settings.PRESETS) == 8, [p["name"] for p in llm_settings.PRESETS])
        names = [p["name"] for p in llm_settings.PRESETS]
        ok("含 DeepSeek/通义/智谱", all(n in names for n in ("DeepSeek", "通义千问", "智谱 GLM")))
        ok("预设能被识别", (llm_settings.match_preset({"base_url": "https://api.deepseek.com"}) or {}).get("id") == "deepseek")
        ok("自定义不匹配", llm_settings.match_preset({"base_url": "https://example.com/v1"}) is None)
        for preset in llm_settings.PRESETS:
            st_ok, reason = llm_settings.status({**preset, "api_key": "sk-x" if "127.0.0.1" not in preset["base_url"] else ""})
            ok(f"预设可用 · {preset['name']}", st_ok, reason)

        # ---------- 3. 时间归一 ----------
        ok("ISO 带分钟", provider.coerce_deadline("2026-11-23T21:30").strftime("%H:%M") == "21:30")
        ok("空格分隔", provider.coerce_deadline("2026-11-23 07:05").strftime("%H:%M") == "07:05")
        ok("只有日期落到 23:59", provider.coerce_deadline("2026-12-01").strftime("%H:%M") == "23:59")
        ok("null 字符串", provider.coerce_deadline("null") is None)
        ok("非法日期", provider.coerce_deadline("2026-02-30") is None)
        ok("剥离代码围栏", provider.extract_json('```json\n{"a":1}\n```')["a"] == 1)

        # ---------- 4. 大模型解析 ----------
        parsed, label, reason = provider.parse_notice(
            "数学分析第 4 次作业，明晚九点半前交。", mode="real",
            base_url=MOCK_URL, model="mock-model", timeout=20,
        )
        ok("标签是大模型", label.startswith("大模型解析"), label)
        ok("无回退原因", reason is None, reason)
        ok("标题来自模型", parsed["title"] == "数学分析第 4 次作业", parsed["title"])
        ok("截止时间解析", parsed["deadline"] == "2026-11-23 21:30", parsed["deadline"])
        ok("可以直接排期", parsed["schedule_ready"] is True and len(build_plan(parsed, 90).get("plan_days", [])) > 0)

        vague, _, _ = provider.parse_notice(
            "英语作文下周交，具体要求课上说了，大家注意格式。", mode="real",
            base_url=MOCK_URL, model="mock-model", timeout=20,
        )
        ok("模糊通知不排期", vague["schedule_ready"] is False and build_plan(vague, 90)["scheduling_engine"] == "blocked")
        ok("标出日期风险", any(r.get("field") == "deadline" for r in vague["risks"]))
        ok("保留格式风险", any("格式" in r["message"] for r in vague["risks"]))
        ok("模型提示可见", any(r.get("type") == "note" for r in vague["risks"]))
        ok("阻断后置信度封顶", vague["confidence"] <= 0.6)

        multi, _, _ = provider.parse_notice(
            "C语言实验报告和代码，周二 18:00 前要交。", mode="real",
            base_url=MOCK_URL, model="mock-model", timeout=20,
        )
        ok("多 DDL 两项", len(multi["ddl_items"]) == 2, len(multi["ddl_items"]))
        ok("多 DDL 取最早", multi["deadline_iso"].startswith("2026-11-24T18:00"))
        ok("每项都有任务", all(item["tasks"] for item in multi["ddl_items"]))
        ok("写作类任务不是 15 分钟", multi["ddl_items"][0]["tasks"][0]["minutes"] == 35,
           multi["ddl_items"][0]["tasks"][0]["minutes"])

        fallback, fb_label, fb_reason = provider.parse_notice(
            "明天交作业", mode="real", base_url="http://127.0.0.1:1/v1", model="x", timeout=5,
        )
        ok("失败回退本地规则", "回退" in fb_label and fallback["raw_text"])
        ok("回退原因可读", fb_reason and "连不上" in fb_reason, fb_reason)

        conn_ok, conn_msg = provider.test_connection(base_url=MOCK_URL, model="mock-model", api_key="sk-mock", timeout=20)
        ok("测试连接成功", conn_ok and "连上了" in conn_msg, conn_msg)
        conn_bad, conn_bad_msg = provider.test_connection(base_url="http://127.0.0.1:1/v1", model="x", api_key="k", timeout=3)
        ok("测试连接失败有原因", (not conn_bad) and conn_bad_msg, conn_bad_msg)

        # ---------- 5. 手动确认截止时间 ----------
        fixed = deadline_tools.apply_manual_deadline(vague, datetime.now(provider.APP_TIMEZONE) + timedelta(days=1))
        ok("写入手动时间", fixed["deadline_basis"] == "manual" and fixed["schedule_ready"] is True)
        ok("清掉日期风险", not any(r.get("field") == "deadline" for r in fixed["risks"]))
        ok("保留其他风险", any("格式" in r["message"] for r in fixed["risks"]))
        ok("手动后能排期", len(build_plan(fixed, 90).get("plan_days", [])) > 0)

        target_time = datetime.now(provider.APP_TIMEZONE) + timedelta(days=3)
        item_fixed = deadline_tools.apply_manual_deadline(multi, target_time, "DDL2")
        ok("只改指定项", item_fixed["ddl_items"][1]["deadline_iso"].startswith(target_time.strftime("%Y-%m-%d")))
        ok("其他项不动", item_fixed["ddl_items"][0]["deadline_iso"].startswith("2026-11-24"))
        ok("整条取最早", item_fixed["deadline_iso"].startswith("2026-11-24"))

        # ---------- 6. 界面（AppTest 真跑） ----------
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(ROOT / "work" / "app.py"), default_timeout=90)
        at.run()
        ok("首页无异常", not at.exception, str(at.exception[:1]))
        at.segmented_control[0].set_value("设置").run()
        ok("设置页能打开", not at.exception and any(t.label == "用大模型解析通知" for t in at.toggle))
        at.toggle[0].set_value(True).run()
        preset_labels = [b.label for b in at.button]
        ok("预设按钮齐全", all(any(name in label for label in preset_labels) for name in ("DeepSeek", "通义千问", "智谱 GLM")),
           preset_labels[:8])
        at.button(key="preset_deepseek").click().run()
        ok("点预设填地址", at.session_state.get("llm_base_url", "").startswith("https://api.deepseek.com"))
        ok("点预设填模型", at.session_state.get("llm_model") == "deepseek-chat")
        at.button(key="preset_zhipu").click().run()
        ok("切预设生效", at.session_state.get("llm_base_url", "").endswith("/paas/v4"))

        at.text_input(key="llm_base_url").set_value(MOCK_URL).run()
        at.text_input(key="llm_model").set_value("mock-model").run()
        at.text_input(key="llm_api_key").set_value("sk-mock").run()
        at.number_input(key="llm_timeout").set_value(20).run()
        at.button(key="llm_test_button").click().run()
        ok("界面测试连接", any("连上了" in s.value for s in at.success), [s.value for s in at.success])
        at.button(key="llm_save_button").click().run()
        ok("界面保存配置", llm_settings.load()["enabled"] is True and llm_settings.load()["model"] == "mock-model")

        at2 = AppTest.from_file(str(ROOT / "work" / "app.py"), default_timeout=90)
        at2.run()
        at2.text_area(key="notice_text").set_value("英语作文下周交，具体要求课上说了，大家注意格式。").run()
        at2.button(key="guided_parse").click().run()
        ok("大模型解析进第 2 步", not at2.exception and at2.session_state["parsed"]["schedule_ready"] is False)
        ok("未确认时计划按钮禁用", at2.button(key="guided_make_plan").disabled is True)
        ok("出现日历选时", any(d.key.startswith("confirm_date_") for d in at2.date_input) and
           any(t.key.startswith("confirm_time_") for t in at2.time_input))

        tomorrow = date.today() + timedelta(days=1)
        at2.date_input(key="confirm_date_0_DDL1").set_value(tomorrow)
        at2.time_input(key="confirm_time_0_DDL1").set_value(dtime(21, 30))
        at2.button(key="confirm_deadlines").click().run()
        ok("确认后可以排期", at2.button(key="guided_make_plan").disabled is False)
        ok("记录为手动确认", at2.session_state["parsed"].get("deadline_basis") == "manual")
        ok("确认后时间正确", at2.session_state["parsed"]["deadline"] == f"{tomorrow.strftime('%Y-%m-%d')} 21:30",
           at2.session_state["parsed"]["deadline"])

        at2.button(key="guided_make_plan").click().run()
        ok("生成计划成功", bool(at2.session_state.get("plan")) and len(at2.session_state["plan"].get("plan_days", [])) > 0)

        # 明确截止时间的通知：不该出现确认块
        at3 = AppTest.from_file(str(ROOT / "work" / "app.py"), default_timeout=90)
        at3.run()
        at3.text_area(key="notice_text").set_value("【数学分析】第 3 次作业：完成习题 1-5。明天23:59前提交。").run()
        at3.button(key="guided_parse").click().run()
        ok("明确时间不出现确认块", not any(d.key.startswith("confirm_date_") for d in at3.date_input))
        ok("明确时间计划按钮可用", at3.button(key="guided_make_plan").disabled is False)

    finally:
        mock.terminate()
        try:
            mock.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock.kill()
        os.environ.pop("DDL_SETTINGS_PATH", None)
        for path in tmpdir.glob("*"):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass

    failed = [item for item in checks if not item[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} 通过")
    if failed:
        print("失败项：", [item[0] for item in failed])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
