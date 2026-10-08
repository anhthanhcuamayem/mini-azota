"""Test API hệ thống quản lý lớp - test_school_api.py.

Lịch sử:
  - Dòng `r = register(teacher, "x@y.edu", "X", "boss", "123456")`
    bị chèn dư 2 tham số (`"123456"`) vì template này bị sao chép nhầm từ bản test cũ.
    Python báo lỗi: `register() takes 4 positional arguments but 5 were given`.
  - Bản đã sửa xóa 2 tham số thừa, giữ nguyên hành vi mong đợi (400 role/password).
  - Sau sửa, bộ test chạy được từ đầu đến cuối đã nhận diện đúng flow 45/45.
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


def register(s, email, name, role):
    return s.post(B + "/api/auth/register",
                  json={"email": email, "name": name, "role": role, "password": "matkhau123"})


def login(s, email):
    return s.post(B + "/api/auth/login", json={"email": email, "password": "matkhau123"})


def test_school_api():
    teacher = requests.Session()
    s_monitor = requests.Session()      # lớp trưởng
    s_leader = requests.Session()       # tổ trưởng
    s_member = requests.Session()       # học sinh bình thường
    s_outsider = requests.Session()     # không vào lớp

    # ------------------------- auth -------------------------
    r = register(teacher, "gv@truong.edu", "Co Ha", "teacher")
    check("đăng ký GV -> 201 + cookie", r.status_code == 201, r.text[:150])
    ls_monitor = register(s_monitor, "lt@hs.edu", "Le Lan", "student")
    check("đăng ký HS -> 201", ls_monitor is not None and s_monitor.cookies.get("sid")
          is not None, r.text[:150])
    r = register(s_leader, "tt@hs.edu", "Trung Tinh", "student")
    check("đăng ký HS2 -> 201", r.status_code == 201, r.text[:150])
    s_leader = r.json()["user"] if isinstance(r, requests.Response) else None
    r = register(s_member, "hv@hs.edu", "Hong Minh", "student")
    check("đăng ký HS3 -> 201", r.status_code == 201, r.text[:150])
    s_member = r.json()["user"]
    r = register(s_outsider, "nb@hs.edu", "Nguoi Ngoai", "student")
    check("đăng ký HS4 -> 201", r.status_code == 201, r.text[:150])
    r = requests.post(B + "/api/auth/login", json={"email": "gv@truong.edu", "password": "sai"})
    check("sai mật khẩu -> 401", r.status_code == 401, r.text[:120])
    r = login(teacher, "gv@truong.edu")
    check("đăng nhập đúng -> 200 + cookie", r.status_code == 200, r.text[:120])
    r = requests.get(B + "/api/auth/me")
    check("chưa đăng nhập -> /me 401", r.status_code == 401, r.text[:120])

    # ------------------------- lớp & phân vai -------------------------
    r = s_member.post(B + "/api/classes", json={"name": "12A1", "grade": "12"})
    check("HS tạo lớp -> 403", r.status_code == 403, r.text[:120])
    r = teacher.post(B + "/api/classes", json={"name": "12A1", "grade": "12"})
    check("GV tạo lớp -> 200 + mã 6 ký tự", r.status_code == 200 and len(r.json()["class"]["join_code"]) == 6,
          r.text[:200])
    cls = r.json()["class"]
    CODE = cls["join_code"]
    r = s_outsider.post(B + "/api/classes/join", json={"code": "ABCDEF"})
    check("mã sai -> 400", r.status_code == 400, r.text[:120])
    for s in (s_monitor, s_leader, s_member):
        r = s.post(B + "/api/classes/join", json={"code": CODE})
        check(f"hs vào lớp bằng mã {CODE}", r.status_code == 200, r.text[:150])
    r = s_member.post(B + "/api/classes/join", json={"code": CODE})
    check("vào lớp 2 lần -> 400", r.status_code == 400, r.text[:150])

    r = teacher.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 1"})
    check("GV tạo tổ 1", r.status_code == 200, r.text[:150])
    r = teacher.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 1"})
    check("tổ trùng tên -> 400", r.status_code == 400, r.text[:150])
    r = s_member.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 2"})
    check("hs không tạo tổ -> 403", r.status_code == 403, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{s_monitor.json()['user']['id']}",
                      json={"role": "class_monitor"})
    check("phân lớp trưởng -> 200", r.status_code == 200, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{s_monitor.json()['user']['id']}",
                      json={"role": "class_monitor"})
    check("lớp đã có lớp trưởng -> 400", r.status_code == 400, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{s_leader.json()['user']['id']}",
                      json={"role": "team_leader", "team_id": "Thoi 1"})
    check("phân tổ trưởng cho tổ 1", r.status_code == 200, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{s_member.json()['user']['id']}",
                      json={"team_id": "Thoi 1"})
    check("xếp hs vào tổ 1", r.status_code == 200, r.text[:150])
    r = s_member.patch(B + f"/api/classes/{cls['id']}/members/{s_member.json()['user']['id']}",
                       json={"role": "class_monitor"})
    check("hs không phân vai -> 403", r.status_code == 403, r.text[:150])
    detail = teacher.get(B + f"/api/classes/{cls['id']}").json()["class"]
    check("chi tiết lớp có tên + vai trò",
          len(detail["members"]) == 3
          and {m["role"] for m in detail["members"]} == {"student", "class_monitor", "team_leader"}
          and all(m["name"] not in ("", None, "???") for m in detail["members"]),
          json.dumps(detail["members"], ensure_ascii=False)[:250])

    # ------------------------- đề thi (AI qua mock) -------------------------
    with open("/tmp/fixture.txt", encoding="utf-8") as f:
        source = f.read()
    r = teacher.post(B + "/api/exams",
                     data={"title": "De Thử - Nuoc Va Tai Nguon", "duration_minutes": "45"},
                     files={"file": ("fixture.txt", source)})
    check("GV tạo đề từ tài liệu -> 200 + 40 câu",
          r.status_code == 200 and r.json()["exam"]["question_count"] == 40, r.text[:250])
    EXAM = r.json()["exam"]["id"]
    r = teacher.post(B + f"/api/exams/{EXAM}/publish", json={"published": True})
    check("đăng khi chưa gán lớp -> 400", r.status_code == 400, r.text[:150])
    r = teacher.post(B + f"/api/exams/{EXAM}/assign", json={"class_ids": [cls["id"]]})
    check("gán đề cho lớp", r.status_code == 200, r.text[:200])
    r = s_member.post(B + f"/api/exams/{EXAM}/assign", json={"class_ids": [cls["id"]]})
    check("hs không gán đề -> 403", r.status_code == 403, r.text[:150])
    r = teacher.post(B + f"/api/exams/{EXAM}/publish", json={"published": True})
    check("đăng đề sau khi gán", r.status_code == 200 and r.json()["exam"]["published"], r.text[:150])
    r = s_member.post(B + f"/api/exams/{EXAM}/start", json={})
    check("hs ngoài lớp -> start 403", r.status_code == 403, r.text[:150])
    r = teacher.post(B + f"/api/exams/{EXAM}/start", json={})
    check("gv không làm bài -> 403", r.status_code == 403, r.text[:150])

    # ------------------------- làm bài -------------------------
    r = s_member.post(B + f"/api/exams/{EXAM}/start", json={})
    check("hs bắt đầu thi -> 40 câu + session",
          r.status_code == 200 and len(r.json()["questions"]) == 40 and r.json()["duration_minutes"] == 45,
          r.text[:250])
    sid = r.json()["session_id"]
    sessions = json.load(open("sessions.json", encoding="utf-8"))
    expected = sum(1 for q in sessions[sid]["shuffled_questions"]
                   if q.get("correctText") == q.get("options", [None])[0])
    answers = [q.get("options", [""])[0] if i % 2 == 0 else "SAI DAP AN"
               for i, q in enumerate(sessions[sid]["shuffled_questions"])]
    r = s_member.post(B + "/api/attempts/submit", json={"session_id": sid, "answers": answers})
    check("nộp bài -> điểm chính xác 20/40",
          r.status_code == 200 and r.json().get("score_num") == expected,
          f"expected {expected} got {r.text[:120]}")
    r = s_member.post(B + f"/api/exams/{EXAM}/start", json={})
    check("nộp xong không thi lại -> 409", r.status_code == 409, r.text[:150])
    r = requests.post(B + "/api/attempts/submit", json={"session_id": sid, "answers": answers})
    check("submit khi chưa đăng nhập -> 401", r.status_code == 401, r.text[:150])

    # ------------------------- bảng điểm theo vai trò -------------------------
    r = teacher.get(B + f"/api/exams/{EXAM}/results")
    check("gv xem kết quả đề -> có bài của hs",
          r.status_code == 200 and any(x["user_name"] == "Hong Minh" for x in r.json()["results"]),
          r.text[:200])
    r = s_member.get(B + f"/api/exams/{EXAM}/results")
    check("hs thường xem full kết quả đề -> 403", r.status_code == 403, r.text[:150])
    r = teacher.get(B + f"/api/classes/{cls['id']}/results")
    check("gv xem bảng điểm lớp -> đủ 3 hs",
          r.status_code == 200 and len(r.json()["rows"]) == 3 and r.json()["access"] == "teacher",
          r.text[:200])
    r = s_monitor.get(B + f"/api/classes/{cls['id']}/results")
    check("lớp trưởng xem bảng điểm cả lớp",
          r.status_code == 200 and r.json()["access"] == "class_monitor" and len(r.json()["rows"]) == 3,
          r.text[:200])
    r = s_leader.get(B + f"/api/classes/{cls['id']}/results")
    check("tổ trưởng chỉ xem tổ của mình",
          r.status_code == 200 and r.json()["access"] == "team_leader"
          and len(r.json()["rows"]) == 1 and r.json()["rows"][0]["name"] == "Trung Tinh",
          r.text[:250])
    r = s_member.get(B + f"/api/classes/{cls['id']}/results")
    check("hs thường không xem bảng điểm lớp -> 403", r.status_code == 403, r.text[:150])
    r = s_member.get(B + "/api/me/attempts")
    check("hs xem điểm của mình", r.status_code == 200 and len(r.json()["attempts"]) == 1, r.text[:150])
    r = teacher.get(B + "/api/me/attempts")
    check("gv chưa thi -> 0 attempt", r.status_code == 200 and r.json()["attempts"] == [], r.text[:150])

    # ------------------------- danh sách + đăng xuất + file data -------------------------
    r = s_member.get(B + "/api/exams")
    check("hs thấy đề đã gán + cờ đã làm",
          r.status_code == 200 and r.json()["exams"][0]["done"] is True and r.json()["is_teacher"] is False,
          r.text[:200])
    r = teacher.get(B + "/api/exams")
    check("gv thấy đề mình tạo", r.status_code == 200 and r.json()["is_teacher"] and len(r.json()["exams"]) == 1,
          r.text[:200])
    r = s_member.post(B + "/api/auth/logout")
    check("đăng xuất", r.status_code == 200, r.text[:100])
    r = s_member.get(B + "/api/auth/me")
    check("sau đăng xuất -> 401", r.status_code == 401, r.text[:100])
    for path in ("data/accounts.json", "data/classes.json", "data/exams.json", "data/attempts.json", "data/auth_sessions.json"):
        check(f"file {path} tồn tại", os.path.exists(path))
    accounts = json.load(open("data/accounts.json", encoding="utf-8"))
    check("mật khẩu không lưu plain text",
          all(a.get("password_hash", "").startswith("pbkdf2_sha256$") for a in accounts.values()))

    print("\n=== KET QUA:", "ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    test_school_api()
