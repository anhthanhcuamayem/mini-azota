"""Lưu trữ JSON cho hệ thống quản lý lớp học & đề thi.

Các file nằm trong data/ :
  accounts.json    - tài khoản (giáo viên / học sinh)
  auth_sessions.json - phiên đăng nhập (cookie sid)
  classes.json     - lớp học, tổ, thành viên, vai trò
  exams.json       - ngân hàng đề + đề đã gán lớp
  attempts.json    - bài đã nộp

Phân vai trong một lớp:
  role = "student" | "class_monitor" (lớp trưởng) | "team_leader" (tổ trưởng)
"""
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
AUTH_FILE = os.path.join(DATA_DIR, "auth_sessions.json")
CLASSES_FILE = os.path.join(DATA_DIR, "classes.json")
EXAMS_FILE = os.path.join(DATA_DIR, "exams.json")
ATTEMPTS_FILE = os.path.join(DATA_DIR, "attempts.json")
SESSIONS_FILE = "sessions.json"  # chung với phiên làm bài của main.py

SESSION_TTL_DAYS = 30
MEMBER_ROLES = {"student", "class_monitor", "team_leader"}
PASSWORD_ITERATIONS = 200_000


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- tài khoản
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False


def create_account(email, name, role, password):
    """Trả về (tài khoản, None) hoặc (None, lỗi)."""
    email = (email or "").strip().lower()
    name = (name or "").strip()
    if role not in ("teacher", "student"):
        return None, "Vai trò không hợp lệ (teacher hoặc student)."
    if "@" not in email or len(email) < 5:
        return None, "Email không hợp lệ."
    if not name or len(name) > 60:
        return None, "Họ tên phải từ 1-60 ký tự."
    if not password or len(password) < 6:
        return None, "Mật khẩu phải có ít nhất 6 ký tự."
    accounts = _read(ACCOUNTS_FILE, {})
    if any(a.get("email") == email for a in accounts.values()):
        return None, "Email đã được đăng ký."
    uid = uuid.uuid4().hex[:12]
    account = {
        "id": uid,
        "email": email,
        "name": name,
        "role": role,
        "password_hash": hash_password(password),
        "created_at": _now(),
    }
    accounts[uid] = account
    _write(ACCOUNTS_FILE, accounts)
    return public_account(account), None


def get_account(user_id):
    return _read(ACCOUNTS_FILE, {}).get(user_id)


def find_account_by_email(email):
    email = (email or "").strip().lower()
    for acc in _read(ACCOUNTS_FILE, {}).values():
        if acc.get("email") == email:
            return acc
    return None


def public_account(acc):
    if not acc:
        return None
    return {k: acc[k] for k in ("id", "email", "name", "role", "created_at") if k in acc}


def login(email, password):
    acc = find_account_by_email(email)
    if not acc or not verify_password(password or "", acc.get("password_hash", "")):
        return None, "Email hoặc mật khẩu không đúng."
    return public_account(acc), None


# ---------------------------------------------------------------- phiên đăng nhập
def create_auth_session(user_id):
    token = secrets.token_urlsafe(32)
    sessions = _read(AUTH_FILE, {})
    sessions[token] = {"user_id": user_id, "created_at": _now()}
    _write(AUTH_FILE, sessions)
    return token


def user_from_token(token):
    if not token:
        return None
    sessions = _read(AUTH_FILE, {})
    sess = sessions.get(token)
    if not sess:
        return None
    try:
        created = datetime.fromisoformat(sess["created_at"])
    except (ValueError, KeyError):
        return None
    if datetime.now(timezone.utc) - created > timedelta(days=SESSION_TTL_DAYS):
        sessions.pop(token, None)
        _write(AUTH_FILE, sessions)
        return None
    return get_account(sess["user_id"])


def destroy_auth_session(token):
    sessions = _read(AUTH_FILE, {})
    if token in sessions:
        sessions.pop(token, None)
        _write(AUTH_FILE, sessions)


# ---------------------------------------------------------------- lớp & tổ
def _new_code(classes):
    while True:
        code = secrets.token_hex(3).upper()  # 6 ký tự, ví dụ 4F2A9C
        if not any(c.get("join_code") == code for c in classes.values()):
            return code


def create_class(teacher_id, name, grade=""):
    name = (name or "").strip()
    if not name or len(name) > 60:
        return None, "Tên lớp phải từ 1-60 ký tự."
    classes = _read(CLASSES_FILE, {})
    cid = uuid.uuid4().hex[:10]
    item = {
        "id": cid,
        "name": name,
        "grade": (grade or "").strip()[:30],
        "teacher_id": teacher_id,
        "join_code": _new_code(classes),
        "teams": [],
        "members": [],
        "created_at": _now(),
    }
    classes[cid] = item
    _write(CLASSES_FILE, classes)
    return item, None


def get_class(class_id):
    return _read(CLASSES_FILE, {}).get(class_id)


def find_class_by_code(code):
    code = (code or "").strip().upper()
    for c in _read(CLASSES_FILE, {}).values():
        if c.get("join_code") == code:
            return c
    return None


def classes_of_teacher(teacher_id):
    return [c for c in _read(CLASSES_FILE, {}).values() if c.get("teacher_id") == teacher_id]


def classes_of_student(user_id):
    return [c for c in _read(CLASSES_FILE, {}).values()
            if any(m.get("user_id") == user_id for m in c.get("members", []))]


def member_of(class_item, user_id):
    for m in class_item.get("members", []):
        if m.get("user_id") == user_id:
            return m
    return None


def join_class(class_code, user_id):
    cls = find_class_by_code(class_code)
    if not cls:
        return None, "Mã lớp không đúng."
    if cls.get("teacher_id") == user_id:
        return None, "Bạn là giáo viên của lớp này."
    if member_of(cls, user_id):
        return None, "Bạn đã ở trong lớp này."
    cls["members"].append({
        "user_id": user_id,
        "team_id": None,
        "role": "student",
        "joined_at": _now(),
    })
    _save_class(cls)
    return cls, None


def _save_class(cls):
    classes = _read(CLASSES_FILE, {})
    classes[cls["id"]] = cls
    _write(CLASSES_FILE, classes)


def add_team(class_id, name, actor_id):
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    if cls.get("teacher_id") != actor_id:
        return None, "Chỉ giáo viên chủ nhiệm mới tạo được tổ."
    name = (name or "").strip()
    if not name:
        return None, "Tên tổ không được rỗng."
    if any(t.get("name") == name for t in cls.get("teams", [])):
        return None, "Tồn tại tổ trùng tên."
    team = {"id": uuid.uuid4().hex[:8], "name": name[:40]}
    cls.setdefault("teams", []).append(team)
    _save_class(cls)
    return team, None


def remove_team(class_id, team_id, actor_id):
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    if cls.get("teacher_id") != actor_id:
        return None, "Chỉ giáo viên chủ nhiệm mới xóa được tổ."
    cls["teams"] = [t for t in cls.get("teams", []) if t.get("id") != team_id]
    for m in cls.get("members", []):
        if m.get("team_id") == team_id:
            m["team_id"] = None
            if m.get("role") == "team_leader":
                m["role"] = "student"
    _save_class(cls)
    return cls, None


def set_member(class_id, actor_id, user_id, role=None, team_id=None):
    """Giáo viên phân vai / xếp tổ cho thành viên."""
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    if cls.get("teacher_id") != actor_id:
        return None, "Chỉ giáo viên chủ nhiệm mới phân vai được."
    member = member_of(cls, user_id)
    if not member:
        return None, "Học sinh này không có trong lớp."
    if role is not None:
        if role not in MEMBER_ROLES:
            return None, "Vai trò không hợp lệ."
        if role == "class_monitor" and any(
            m.get("role") == "class_monitor" and m.get("user_id") != user_id
            for m in cls["members"]
        ):
            return None, "Lớp đã có lớp trưởng. Bỏ vai trò của lớp trưởng cũ trước."
        if role == "class_monitor":
            member["team_id"] = None  # lớp trưởng không thuộc tổ cụ thể
        member["role"] = role
    if team_id is not None:
        if team_id == "":
            member["team_id"] = None
        elif not any(t.get("id") == team_id for t in cls.get("teams", [])):
            return None, "Tổ không tồn tại trong lớp."
        else:
            member["team_id"] = team_id
    _save_class(cls)
    return cls, None


def remove_member(class_id, actor_id, user_id):
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    if cls.get("teacher_id") != actor_id:
        return None, "Chỉ giáo viên chủ nhiệm mới xóa thành viên được."
    before = len(cls["members"])
    cls["members"] = [m for m in cls["members"] if m.get("user_id") != user_id]
    if len(cls["members"]) == before:
        return None, "Thành viên không có trong lớp."
    _save_class(cls)
    return cls, None


def class_with_names(cls):
    """Lớp kèm họ tên + email thành viên (cho UI)."""
    accounts = _read(ACCOUNTS_FILE, {})
    out = dict(cls)
    out["members"] = [
        {**m, "name": accounts.get(m.get("user_id"), {}).get("name", "???"),
         "email": accounts.get(m.get("user_id"), {}).get("email", "")}
        for m in cls.get("members", [])
    ]
    out["teacher_name"] = accounts.get(cls.get("teacher_id"), {}).get("name", "")
    return out


# ---------------------------------------------------------------- đề thi
def create_exam(created_by, title, duration_minutes=60, questions=None,
                 source_text="", filename="", mode="shared"):
    title = (title or "").strip()
    if not title or len(title) > 120:
        return None, "Tên đề thi phải từ 1-120 ký tự."
    exams = _read(EXAMS_FILE, {})
    eid = uuid.uuid4().hex[:10]
    exam = {
        "id": eid,
        "title": title,
        "created_by": created_by,
        "mode": mode,
        "duration_minutes": int(duration_minutes or 60),
        "questions": questions or [],
        "source_text": source_text,
        "filename": filename,
        "class_ids": [],
        "published": False,
        "start_at": None,
        "end_at": None,
        "created_at": _now(),
    }
    exams[eid] = exam
    _write(EXAMS_FILE, exams)
    return exam, None


def get_exam(exam_id):
    return _read(EXAMS_FILE, {}).get(exam_id)


def _save_exam(exam):
    exams = _read(EXAMS_FILE, {})
    exams[exam["id"]] = exam
    _write(EXAMS_FILE, exams)


def exams_of_teacher(teacher_id):
    return [e for e in _read(EXAMS_FILE, {}).values() if e.get("created_by") == teacher_id]


def exams_for_student(user_id, classes):
    """Đề đã xuất bản và được gán cho lớp mà học sinh đang ở trong."""
    class_ids = {c["id"] for c in classes}
    return [e for e in _read(EXAMS_FILE, {}).values()
            if e.get("published") and class_ids.intersection(e.get("class_ids", []))]


def assign_exam(exam_id, actor_id, class_ids):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới gán đề được."
    if not isinstance(class_ids, list) or not class_ids:
        return None, "Danh sách lớp không hợp lệ."
    teacher_classes = {c["id"] for c in classes_of_teacher(actor_id)}
    missing = [cid for cid in class_ids if cid not in teacher_classes]
    if missing:
        return None, "Bạn không quản lý lớp: " + ", ".join(missing)
    exam["class_ids"] = list(class_ids)
    _save_exam(exam)
    return exam, None


def set_publish(exam_id, actor_id, published):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới đăng/ẩn đề được."
    if not exam.get("questions"):
        return None, "Đề chưa có câu hỏi (hãy tạo câu hỏi trước khi đăng)."
    if published and not exam.get("class_ids"):
        return None, "Hãy gán đề cho ít nhất một lớp trước khi đăng."
    exam["published"] = bool(published)
    _save_exam(exam)
    return exam, None


def set_schedule(exam_id, actor_id, start_at=None, end_at=None):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới đổi lịch được."
    exam["start_at"] = start_at or None
    exam["end_at"] = end_at or None
    _save_exam(exam)
    return exam, None


def delete_exam(exam_id, actor_id):
    exams = _read(EXAMS_FILE, {})
    exam = exams.get(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới xóa được."
    exams.pop(exam_id, None)
    _write(EXAMS_FILE, exams)
    return True, None


def replace_questions(exam_id, actor_id, questions):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới đổi câu hỏi được."
    exam["questions"] = questions
    _save_exam(exam)
    return exam, None


# ---------------------------------------------------------------- phiên thi & bài nộp
def save_exam_session(session_id, name, start_time, questions, user_id, exam_id):
    sessions = _read(SESSIONS_FILE, {})
    sessions[session_id] = {
        "name": name,
        "user_id": user_id,
        "exam_id": exam_id,
        "start_time": start_time.isoformat(),
        "shuffled_questions": questions,
    }
    _write(SESSIONS_FILE, sessions)


def get_exam_session(session_id):
    return _read(SESSIONS_FILE, {}).get(session_id)


def delete_exam_session(session_id):
    sessions = _read(SESSIONS_FILE, {})
    if session_id in sessions:
        sessions.pop(session_id, None)
        _write(SESSIONS_FILE, sessions)


def save_attempt(attempt):
    attempts = _read(ATTEMPTS_FILE, [])
    attempts.append(attempt)
    _write(ATTEMPTS_FILE, attempts)
    return attempt


def attempts_of_exam(exam_id):
    return [a for a in _read(ATTEMPTS_FILE, []) if a.get("exam_id") == exam_id]


def attempts_of_user(user_id):
    return [a for a in _read(ATTEMPTS_FILE, []) if a.get("user_id") == user_id]


def has_attempt(exam_id, user_id):
    return any(a.get("exam_id") == exam_id and a.get("user_id") == user_id
               for a in _read(ATTEMPTS_FILE, []))


def attempts_in_classes(exam_ids, member_ids):
    """Bài nộp của các thành viên trong các đề đã cho (dùng cho bảng điểm)."""
    wanted_exams = set(exam_ids)
    wanted_users = set(member_ids)
    return [a for a in _read(ATTEMPTS_FILE, [])
            if a.get("exam_id") in wanted_exams and a.get("user_id") in wanted_users]
