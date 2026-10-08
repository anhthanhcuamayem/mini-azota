"""Mock server OpenAI-compatible để test pipeline sinh đề mà không cần API key thật.

Chạy: python3 tests/mock_ai.py [ok|garbage|partial] [port]
  GET  /            -> {"calls": n, "mode": ...}
  POST /v1/chat/completions -> phản hồi chuẩn chat/completions
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = sys.argv[1] if len(sys.argv) > 1 else "ok"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9099
CALLS = {"n": 0}


def _questions(n, count):
    return [
        {
            # số đếm trong đề để chứng minh mock được gọi ở lượt nào
            "text": f"[mock call {n}] Câu {i + 1}: nội dung rút từ tài liệu là gì?",
            "options": [f"Phương án {i + 1}A", f"Phương án {i + 1}B",
                        f"Phương án {i + 1}C", f"Phương án {i + 1}D"],
            "answer": "ABCD"[i % 4],
        }
        for i in range(count)
    ]


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"calls": CALLS["n"], "mode": MODE})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        CALLS["n"] += 1
        prompt = next((m.get("content", "") for m in body.get("messages", [])
                       if m.get("role") == "user"), "")
        match = re.search(r"viết đúng (\d+) câu", prompt)
        needed = int(match.group(1)) if match else 40

        if MODE == "garbage":
            content = "Xin lỗi, tôi không thể làm điều đó."
        elif MODE == "partial":
            content = json.dumps(_questions(CALLS["n"], max(1, needed // 2)),
                                 ensure_ascii=False)
        else:
            content = json.dumps(_questions(CALLS["n"], needed), ensure_ascii=False)
        self._send({"choices": [{"message": {"role": "assistant", "content": content}}]})

    def log_message(self, *args):
        print(f"[mock {MODE}] call#{CALLS['n']}", flush=True)


if __name__ == "__main__":
    print(f"mock AI on 127.0.0.1:{PORT} mode={MODE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
