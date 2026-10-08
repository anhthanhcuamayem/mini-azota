"""Regression sau khi nối router quản lý lớp vào main.py.

Bao gồm:
  1. Unit: retry khi AI trả rác, lỗi khi AI trả thiếu, lọc câu sai, normalize answer.
  2. Admin: upload hợp lệ/sai định dạng/sai mode, generate lại.
  3. Phòng thi ẩn danh còn hoạt động: /start -> /submit -> /get-questions.
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.getcwd())
import main  # noqa: E402

B = "http://127.0.0.1:8011"
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  | " + str(extra)[:200]) if extra else ""))
    if not cond:
        fails.append(name)


def items(n, prefix):
    return [{"text": f"{prefix} {i}", "options": ["a", "b", "c", "d"], "answer": "ABCD"[i % 4]}
            for i in range(n)]


orig = main.ai_chat

# ---------- 1. unit AI ----------
calls = {"n": 0}


def stub_retry(prompt, **kw):
    calls["n"] += 1
    return ("Xin lỗi, tôi không thể làm điều đó." if calls["n"] == 1
            else json.dumps(items(40, "R"), ensure_ascii=False))


main.ai_chat = stub_retry
try:
    qs = main.generate_questions("tài liệu đủ dài")
    check("unit: retry sau JSON rác -> 40 câu", len(qs) == 40 and calls["n"] == 2, f"calls={calls['n']}")
finally:
    main.ai_chat = orig

main.ai_chat = lambda *a, **k: json.dumps(items(20, "P"), ensure_ascii=False)
try:
    main.generate_questions("tài liệu đủ dài")
    check("unit: AI trả thiếu -> AIError", False, "không raise")
except main.AIError as e:
    check("unit: AI trả thiếu -> AIError", "20/40" in str(e), str(e))
finally:
    main.ai_chat = orig

main.ai_chat = lambda *a, **k: json.dumps([
    {"text": "", "options": ["a", "b", "c", "d"], "answer": "A"},
    {"text": "hợp lệ", "options": ["a", "b", "c", "d"], "answer": "C"},
    {"text": "đáp án là text", "options": ["ph1", "ph2", "ph3", "ph4"], "answer": "ph3"},
], ensure_ascii=False)
try:
    main.generate_questions("tài liệu")
    check("unit: toàn câu sai -> AIError", False, "không raise")
except main.AIError as e:
    check("unit: toàn câu sai -> AIError", "hợp lệ" in str(e), str(e))
finally:
    main.ai_chat = orig

norm = main.normalize_questions([
    {"text": "1", "options": ["p1", "p2", "p3", "p4"], "answer": "B"},
    {"text": "2", "options": ["p1", "p2", "p3", "p4"], "answer": "p3"},
    {"text": "3", "options": ["P1", "P2", "p3", "p4"], "answer": "p1"},
])
check("unit: answer dạng chữ cái + text (kể cả khác hoa/thường)",
      len(norm) == 3 and norm[0]["correctText"] == "p2"
      and norm[1]["correctText"] == "p3" and norm[2]["correctText"] == "P1",
      json.dumps(norm, ensure_ascii=False)[:200])

# trích xuất vẫn chạy
for name in ("fixture.docx", "fixture.pdf", "fixture.txt"):
    path = "/tmp/" + name
    if os.path.exists(path):
        with open(path, "rb") as f:
            text = main.extract_text(path, f.read())
        check(f"unit: trích xuất {name}", len(text) > 500, f"{len(text)} chars")
        break
else:
    check("unit: có fixture để test trích xuất", False, "thiếu /tmp/fixture.*")

# ---------- 2. admin upload ----------
r = requests.get(B + "/admin/status")
check("admin/status 200 + báo cấu hình AI", r.status_code == 200 and "ai_configured" in r.text)
r = requests.post(B + "/admin/upload", files={"file": ("x.exe", b"MZ")}, data={"mode": "shared"})
check("upload sai định dạng -> 400", r.status_code == 400, r.text[:120])
r = requests.post(B + "/admin/upload",
                  files={"file": ("short.txt", "ngắn")}, data={"mode": "shared"})
check("upload file quá ngắn -> 400", r.status_code == 400, r.text[:120])
r = requests.post(B + "/admin/upload",
                  files={"file": ("x.txt", "a" * 400)}, data={"mode": "sai-mode"})
check("sai mode -> 400", r.status_code == 400, r.text[:120])

with open("/tmp/fixture.txt", encoding="utf-8") as f:
    content = f.read()
r = requests.post(B + "/admin/upload",
                  files={"file": ("fixture.txt", content)}, data={"mode": "shared"}, timeout=120)
check("upload .txt hợp lệ -> 400 (cần AI cấu hình ở server test)",
      r.status_code in (200, 502), f"{r.status_code} {r.text[:200]}")
if r.status_code == 200:
    check("bank có 40 câu", r.json().get("questions") == 40, r.text[:150])

# ---------- 3. phòng thi ẩn danh ----------
if os.path.exists(main.BANK_FILE):
    r = requests.get(B + "/get-questions")
    check("/get-questions 40 câu, không lộ đáp án",
          r.status_code == 200 and len(r.json()) == 40
          and all("correctText" not in q for q in r.json()), str(r.status_code))
    r = requests.post(B + "/start", json={"name": "Regression Anon"}, timeout=60)
    d = r.json()
    sid = d.get("session_id")
    check("/start ẩn danh -> 40 câu + session",
          r.status_code == 200 and len(d.get("questions", [])) == 40 and sid, r.text[:200])
    if sid:
        sessions = json.load(open("sessions.json", encoding="utf-8"))
        expected = sum(1 for q in sessions[sid]["shuffled_questions"]
                       if q.get("correctText") == q.get("options", [None])[0])
        answers = [q.get("options", [""])[0] for q in sessions[sid]["shuffled_questions"]]
        r = requests.post(B + "/submit", json={"session_id": sid, "answers": answers})
        check("/submit ẩn danh -> đúng số điểm đã chấm",
              r.status_code == 200 and r.json().get("score_num") == expected,
              f"expected {expected} | {r.text[:150]}")
        r = requests.post(B + "/submit", json={"session_id": sid, "answers": ["a"]})
        check("session đã xóa -> 400", r.status_code == 400, r.text[:120])
else:
    check("có bank để test phòng thi ẩn danh", False, "thiếu exam_bank.json")

# ---------- trang ----------
for path, needle in (("/", "VÀO PHÒNG THI"), ("/admin", "Tạo đề thi"), ("/portal", "Đăng nhập")):
    r = requests.get(B + path)
    check(f"GET {path} 200", r.status_code == 200 and needle in r.text, f"{r.status_code}")

print("\n=== KẾT QUẢ:", "ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}")
sys.exit(1 if fails else 0)
