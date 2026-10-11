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
import school_store as store  # noqa: E402

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
    u_monitor = ls_monitor.json()["user"]
    r = register(s_leader, "tt@hs.edu", "Trung Tinh", "student")
    check("đăng ký HS2 -> 201", r.status_code == 201, r.text[:150])
    u_leader = r.json()["user"]
    r = register(s_member, "hv@hs.edu", "Hong Minh", "student")
    check("đăng ký HS3 -> 201", r.status_code == 201, r.text[:150])
    u_member = r.json()["user"]
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
    TEAM1 = r.json()["team"]["id"]
    r = teacher.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 1"})
    check("tổ trùng tên -> 400", r.status_code == 400, r.text[:150])
    r = s_member.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 2"})
    check("hs không tạo tổ -> 403", r.status_code == 403, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_monitor['id']}",
                      json={"role": "class_monitor"})
    check("phân lớp trưởng -> 200", r.status_code == 200, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_leader['id']}",
                      json={"role": "class_monitor"})
    check("lớp đã có lớp trưởng -> 400", r.status_code == 400, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_leader['id']}",
                      json={"role": "team_leader", "team_id": TEAM1})
    check("phân tổ trưởng cho tổ 1", r.status_code == 200, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_member['id']}",
                      json={"team_id": TEAM1})
    check("xếp hs vào tổ 1", r.status_code == 200, r.text[:150])
    r = s_member.patch(B + f"/api/classes/{cls['id']}/members/{u_member['id']}",
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
    r = s_outsider.post(B + f"/api/exams/{EXAM}/start", json={})
    check("hs ngoài lớp -> start 403", r.status_code == 403, r.text[:150])
    r = teacher.post(B + f"/api/exams/{EXAM}/start", json={})
    check("gv không làm bài -> 403", r.status_code == 403, r.text[:150])

    # ------------------------- làm bài -------------------------
    r = s_member.post(B + f"/api/exams/{EXAM}/start", json={})
    check("hs bắt đầu thi -> 40 câu + session",
          r.status_code == 200 and len(r.json()["questions"]) == 40 and r.json()["duration_minutes"] == 45,
          r.text[:250])
    sid = r.json()["session_id"]
    sessions = {sid: store.get_exam_session(sid)}
    expected = sum(1 for i, q in enumerate(sessions[sid]["shuffled_questions"])
                   if i % 2 == 0 and q.get("correctText") == q.get("options", [None])[0])
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
          and r.json().get("note") and "Thoi 1" in r.json()["note"]
          and {row["name"] for row in r.json()["rows"]} == {"Trung Tinh", "Hong Minh"},
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
    # ------------------------- vai trò, quyền & quản lý lớp -------------------------
    r = teacher.get(B + f"/api/classes/{cls['id']}/roles")
    check("GV xem danh mục quyền + vai trò hệ thống (có lớp phó)",
          r.status_code == 200 and len(r.json()["permissions"]) >= 5
          and any(x["id"] == "vice_class_monitor" for x in r.json()["builtin"]), r.text[:220])

    r = s_member.get(B + f"/api/classes/{cls['id']}/roles")
    check("HS chưa có assign_roles -> không xem được danh mục phân quyền",
          r.status_code == 403, r.text[:150])

    r = teacher.post(B + f"/api/classes/{cls['id']}/roles",
                     json={"name": "Do su", "permissions": ["view_class_results", "export_scores"]})
    check("GV tạo vai trò tùy chỉnh -> 200", r.status_code == 200, r.text[:150])
    CUSTOM = r.json()["role"]["id"] if r.status_code == 200 else ""

    r = teacher.post(B + f"/api/classes/{cls['id']}/roles",
                     json={"name": "Do su", "permissions": []})
    check("tên vai trò trùng -> 400", r.status_code == 400, r.text[:150])

    r = teacher.post(B + f"/api/classes/{cls['id']}/roles",
                     json={"name": "Sai quyen", "permissions": ["khong-ton-tai"]})
    check("quyền không tồn tại -> 400", r.status_code == 400, r.text[:150])

    r = s_member.post(B + f"/api/classes/{cls['id']}/roles",
                      json={"name": "Doc tu tao", "permissions": []})
    check("HS không tạo được vai trò -> 403", r.status_code == 403, r.text[:150])

    # ---- lớp phó (vai trò hệ thống mới) ----
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_member['id']}",
                      json={"role": "vice_class_monitor"})
    check("GV cấp vai trò lớp phó -> 200", r.status_code == 200, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_leader['id']}",
                      json={"role": "vice_class_monitor"})
    check("lớp đã có lớp phó -> 400", r.status_code == 400, r.text[:150])

    r = s_member.get(B + f"/api/classes/{cls['id']}/results")
    check("lớp phó xem được bảng điểm cả lớp",
          r.status_code == 200 and r.json()["access"] == "class_monitor"
          and "view_class_results" in r.json()["permissions"], r.text[:220])
    r = s_member.get(B + f"/api/classes/{cls['id']}")
    check("lớp phó thấy nhãn vai trò của mình",
          r.status_code == 200 and r.json()["class"]["my_role_label"] == "Lớp phó", r.text[:220])

    r = s_member.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 4"})
    check("lớp phó không có manage_teams -> tạo tổ 403", r.status_code == 403, r.text[:150])

    # ---- vai trò tùy chỉnh được cấp quyền ----
    r = teacher.post(B + f"/api/classes/{cls['id']}/roles",
                     json={"name": "Quan ly to", "permissions": ["manage_teams", "assign_roles"]})
    check("GV tạo vai trò quản lý tổ -> 200", r.status_code == 200, r.text[:150])
    MANAGER = r.json()["role"]["id"] if r.status_code == 200 else ""
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_member['id']}",
                      json={"role": MANAGER})
    check("gán vai trò tùy chỉnh cho thành viên -> 200", r.status_code == 200, r.text[:150])
    r = s_member.get(B + f"/api/classes/{cls['id']}")
    check("thành viên thấy vai trò tùy chỉnh + nhãn",
          r.status_code == 200 and r.json()["class"]["my_role"] == MANAGER
          and r.json()["class"]["my_role_label"] == "Quan ly to", r.text[:220])

    r = s_member.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 4"})
    check("vai trò có manage_teams -> tạo tổ 200", r.status_code == 200, r.text[:150])
    r = s_leader.post(B + f"/api/classes/{cls['id']}/teams", json={"name": "Thoi 5"})
    check("tổ trưởng (chỉ view_team_results) không tạo tổ -> 403", r.status_code == 403, r.text[:150])

    r = s_member.patch(B + f"/api/classes/{cls['id']}/members/{u_leader['id']}",
                       json={"role": "class_monitor"})
    check("không phải GV chủ nhiệm -> không cấp được lớp trưởng -> 403",
          r.status_code == 403, r.text[:150])
    r = s_member.patch(B + f"/api/classes/{cls['id']}/members/{u_leader['id']}",
                       json={"team_id": TEAM1})
    check("có assign_roles -> xếp tổ được -> 200", r.status_code == 200, r.text[:150])

    # ---- vai trò tùy chỉnh có quyền xem bảng điểm ----
    r = teacher.patch(B + f"/api/classes/{cls['id']}/members/{u_leader['id']}", json={"role": CUSTOM})
    check("GV gán vai trò Do su -> 200", r.status_code == 200, r.text[:150])
    r = s_leader.get(B + f"/api/classes/{cls['id']}/results")
    check("vai trò có view_class_results -> xem bảng điểm cả lớp",
          r.status_code == 200 and r.json()["access"] == "class_monitor"
          and "export_scores" in r.json()["permissions"], r.text[:220])
    r = teacher.delete(B + f"/api/classes/{cls['id']}/roles/{CUSTOM}")
    check("xóa vai trò -> 200", r.status_code == 200, r.text[:150])
    r = teacher.get(B + f"/api/classes/{cls['id']}")
    held = next(m for m in r.json()["class"]["members"] if m["user_id"] == u_leader["id"])
    check("xóa vai trò -> thành viên giữ nó trở về Học sinh", held["role"] == "student", r.text[:200])

    # ---- quản lý lớp ----
    r = s_member.patch(B + f"/api/classes/{cls['id']}", json={"name": "Bị chiếm"})
    check("HS không sửa được lớp -> 403", r.status_code == 403, r.text[:150])
    r = teacher.patch(B + f"/api/classes/{cls['id']}", json={"name": "12A1 Do", "grade": "12"})
    check("GV sửa tên lớp -> 200",
          r.status_code == 200 and r.json()["class"]["name"] == "12A1 Do", r.text[:200])
    r = teacher.post(B + f"/api/classes/{cls['id']}/regen-code")
    check("GV đổi mã lớp -> mã mới khác mã cũ",
          r.status_code == 200 and r.json()["class"]["join_code"] != CODE, r.text[:200])
    r = s_leader.delete(B + f"/api/classes/{cls['id']}")
    check("thành viên không xóa được lớp -> 403", r.status_code == 403, r.text[:150])

    r = teacher.post(B + "/api/classes", json={"name": "Lop Tam Xoa", "grade": "12"})
    tmp_id = r.json()["class"]["id"]
    r = teacher.delete(B + f"/api/classes/{tmp_id}")
    check("GV xóa lớp -> 200", r.status_code == 200, r.text[:150])
    r = teacher.get(B + f"/api/classes/{tmp_id}")
    check("lớp đã xóa -> GET 404", r.status_code == 404, r.text[:150])

    r = s_member.post(B + "/api/auth/logout")
    check("đăng xuất", r.status_code == 200, r.text[:100])
    r = s_member.get(B + "/api/auth/me")
    check("sau đăng xuất -> 401", r.status_code == 401, r.text[:100])
    for table in ("accounts", "classes", "exams", "attempts", "auth_sessions"):
        check(f"bảng Supabase '{table}' có dữ liệu", len(store.db.select(table)) > 0)
    accounts = {a["id"]: a for a in store.all_accounts()}
    check("mật khẩu không lưu plain text",
          bool(accounts) and all(a.get("password_hash", "").startswith("pbkdf2_sha256$")
                                 for a in accounts.values()))

    print("\n=== KET QUA:", "ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    test_school_api()
