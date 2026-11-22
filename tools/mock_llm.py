"""本地假的 OpenAI 兼容服务，给回归测试用。

跑法：
    python tools/mock_llm.py 8801
带 system 提示词的请求按关键词返回结构化 JSON；只有一句 user 请求的（测试连接）返回 OK。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def plan_for(text):
    if "英语作文" in text:
        return {
            "title": "英语作文（下周交）",
            "deadline": None,
            "deadline_source": "下周交",
            "deliverables": ["英语作文"],
            "materials": [],
            "ddl_items": [],
            "notes": "字数和格式要问老师",
            "confidence": 0.62,
        }
    if "实验报告" in text and "代码" in text:
        return {
            "title": "C 语言实验报告＋代码",
            "deadline": "2026-11-24T18:00",
            "deadline_source": "周二 18:00 前",
            "deliverables": ["实验报告", "实验代码"],
            "materials": ["实验数据"],
            "ddl_items": [
                {"title": "实验报告", "deadline": "2026-11-24T18:00", "deliverables": ["写完实验报告并导出 PDF"]},
                {"title": "实验代码", "deadline": "2026-11-25T12:00", "deliverables": ["整理并提交代码"]},
            ],
            "notes": "",
            "confidence": 0.9,
        }
    return {
        "title": "数学分析第 4 次作业",
        "deadline": "2026-11-23T21:30",
        "deadline_source": "明晚九点半",
        "deliverables": ["习题 4-1 到 4-8"],
        "materials": ["教材"],
        "ddl_items": [],
        "notes": "",
        "confidence": 0.88,
    }


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            body = json.loads(raw or "{}")
        except ValueError:
            body = {}

        messages = body.get("messages") or []
        user_text = ""
        has_system = False
        for message in messages:
            role = message.get("role")
            if role == "system":
                has_system = True
            elif role == "user":
                user_text += str(message.get("content") or "")

        if has_system:
            try:
                payload = json.loads(user_text)
                source = "\n".join(item.get("text", "") for item in payload.get("notices", []))
            except ValueError:
                source = user_text
            content = "```json\n" + json.dumps(plan_for(source), ensure_ascii=False) + "\n```"
        else:
            content = "OK"

        data = json.dumps({
            "id": "mock",
            "object": "chat.completion",
            "model": body.get("model") or "mock-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8801
    print(f"mock llm on http://127.0.0.1:{port}/v1", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
