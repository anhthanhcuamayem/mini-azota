"""Lưu trữ cho hệ thống quản lý lớp học & đề thi — dùng Supabase.

Toàn bộ dữ liệu nằm trên Postgres của Supabase (xem supabase_schema.sql):
  accounts        - tài khoản (giáo viên / học sinh)
  auth_sessions   - phiên đăng nhập (cookie sid)
  classes         - lớp học, tổ, thành viên, vai trò
  quizzes         - kho bộ đề nhiều môn (phòng thi ẩn danh)
  exams           - đề đã gán lớp (portal)
  exam_sessions   - phiên đang làm bài
  attempts        - bài đã nộp

Phân vai trong một lớp:
  role = "student" | "class_monitor" (lớp trưởng) | "team_leader" (tổ trưởng)
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import supabase_store as db

SESSION_TTL_DAYS = 30
MEMBER_ROLES = {"student", "class_monitor", "vice_class_monitor", "team_leader"}
PASSWORD_ITERATIONS = 200_000

# ---------------------------------------------------------------- vai trò & quyền
BUILTIN_ROLE_LABELS = {
    "student": "Học sinh",
    "vice_class_monitor": "Lớp phó",
    "class_monitor": "Lớp trưởng",
    "team_leader": "Tổ trưởng",
}
MONITOR_ROLES = ("class_monitor", "vice_class_monitor")

# Danh mục quyền giáo viên có thể cấp cho một vai trò.
PERMISSIONS = {
    "view_class_results": "Xem bảng điểm cả lớp",
    "view_team_results": "Xem bảng điểm tổ của mình",
    "export_scores": "Xuất bảng điểm (CSV)",
    "manage_teams": "Tạo / xóa tổ",
    "assign_roles": "Phân vai trò & xếp tổ (trừ lớp trưởng, lớp phó)",
}

# Quyền mặc định của các vai trò có sẵn (giáo viên luôn có đủ mọi quyền).
BUILTIN_ROLE_PERMS = {
    "student": [],
    "vice_class_monitor": ["view_class_results", "export_scores"],
    "class_monitor": ["view_class_results", "view_team_results", "export_scores", "manage_teams"],
    "team_leader": ["view_team_results"],
}
ALL_PERMISSIONS = set(PERMISSIONS)


def _validate_permissions(permissions):
    """Trả về (list quyền hợp lệ, None) hoặc (None, lỗi)."""
    if permissions is None:
        return [], None
    if not isinstance(permissions, (list, tuple, set)):
        return None, "Danh sách quyền không hợp lệ."
    bad = [str(p) for p in permissions if p not in ALL_PERMISSIONS]
    if bad:
        return None, "Quyền không tồn tại: " + ", ".join(bad)
    return sorted(set(permissions)), None


def _now():
    return datetime.now(timezone.utc).isoformat()


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
    if find_account_by_email(email):
        return None, "Email đã được đăng ký."
    account = {
        "id": uuid.uuid4().hex[:12],
        "email": email,
        "name": name,
        "role": role,
        "password_hash": hash_password(password),
        "created_at": _now(),
    }
    try:
        db.insert("accounts", account)
    except db.SupabaseError:
        return None, "Email đã được đăng ký."
    return public_account(account), None


def get_account(user_id):
    if not user_id:
        return None
    return db.select_one("accounts", [("id", user_id)])


def find_account_by_email(email):
    email = (email or "").strip().lower()
    if not email:
        return None
    return db.select_one("accounts", [("email", email)])


def all_accounts():
    return db.select("accounts")


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
    db.insert("auth_sessions", {"token": token, "user_id": user_id, "created_at": _now()})
    return token


def user_from_token(token):
    if not token:
        return None
    sess = db.select_one("auth_sessions", [("token", token)])
    if not sess:
        return None
    try:
        created = datetime.fromisoformat(sess["created_at"])
    except (ValueError, KeyError, TypeError):
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > timedelta(days=SESSION_TTL_DAYS):
        db.delete("auth_sessions", [("token", token)])
        return None
    return public_account(get_account(sess["user_id"]))


def destroy_auth_session(token):
    if token:
        db.delete("auth_sessions", [("token", token)])


# ---------------------------------------------------------------- lớp & tổ
def _new_code():
    existing = {c.get("join_code") for c in db.select("classes", columns="join_code")}
    while True:
        code = secrets.token_hex(3).upper()  # 6 ký tự, ví dụ 4F2A9C
        if code not in existing:
            return code


def create_class(teacher_id, name, grade=""):
    name = (name or "").strip()
    if not name or len(name) > 60:
        return None, "Tên lớp phải từ 1-60 ký tự."
    item = {
        "id": uuid.uuid4().hex[:10],
        "name": name,
        "grade": (grade or "").strip()[:30],
        "teacher_id": teacher_id,
        "join_code": _new_code(),
        "teams": [],
        "members": [],
        "roles": [],
        "created_at": _now(),
    }
    db.insert("classes", item)
    return item, None


def get_class(class_id):
    if not class_id:
        return None
    return db.select_one("classes", [("id", class_id)])


def find_class_by_code(code):
    code = (code or "").strip().upper()
    if not code:
        return None
    return db.select_one("classes", [("join_code", code)])


def classes_of_teacher(teacher_id):
    return db.select("classes", [("teacher_id", teacher_id)])


def classes_of_student(user_id):
    return [c for c in db.select("classes")
            if any(m.get("user_id") == user_id for m in c.get("members") or [])]


def member_of(class_item, user_id):
    for m in class_item.get("members") or []:
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
    cls.setdefault("members", []).append({
        "user_id": user_id,
        "team_id": None,
        "role": "student",
        "joined_at": _now(),
    })
    _save_class(cls)
    return cls, None


def _save_class(cls):
    db.update("classes", {"teams": cls.get("teams") or [],
                          "members": cls.get("members") or [],
                          "roles": cls.get("roles") or []},
              [("id", cls["id"])])


def add_team(class_id, name):
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    name = (name or "").strip()
    if not name:
        return None, "Tên tổ không được rỗng."
    if any(t.get("name") == name for t in cls.get("teams") or []):
        return None, "Tồn tại tổ trùng tên."
    team = {"id": uuid.uuid4().hex[:8], "name": name[:40]}
    cls.setdefault("teams", []).append(team)
    _save_class(cls)
    return team, None


def remove_team(class_id, team_id):
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    cls["teams"] = [t for t in cls.get("teams") or [] if t.get("id") != team_id]
    for m in cls.get("members") or []:
        if m.get("team_id") == team_id:
            m["team_id"] = None
            if m.get("role") == "team_leader":
                m["role"] = "student"
    _save_class(cls)
    return cls, None


def set_member(class_id, user_id, role=None, team_id=None):
    """Phân vai / xếp tổ cho thành viên (việc cho phép hay không do API quyết định)."""
    cls = get_class(class_id)
    if not cls:
        return None, "Không tìm thấy lớp."
    member = member_of(cls, user_id)
    if not member:
        return None, "Học sinh này không có trong lớp."
    if role is not None:
        custom_ids = {r.get("id") for r in cls.get("roles") or []}
        if role not in MEMBER_ROLES and role not in custom_ids:
            return None, "Vai trò không hợp lệ."
        if role in MONITOR_ROLES and any(
            m.get("role") == role and m.get("user_id") != user_id
            for m in cls["members"]
        ):
            return None, f"Lớp đã có {BUILTIN_ROLE_LABELS[role].lower()}. Hãy bỏ vai trò của người đó trước."
        if role == "class_monitor":
            member["team_id"] = None  # lớp trưởng không thuộc tổ cụ thể
        member["role"] = role
    if team_id is not None:
        if team_id == "":
            member["team_id"] = None
        elif not any(t.get("id") == team_id for t in cls.get("teams") or []):
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
    before = len(cls.get("members") or [])
    cls["members"] = [m for m in cls.get("members") or [] if m.get("user_id") != user_id]
    if len(cls["members"]) == before:
        return None, "Thành viên không có trong lớp."
    _save_class(cls)
    return cls, None


def role_label(cls, role):
    """Tên hiển thị của vai trò (kể cả vai trò tùy chỉnh)."""
    if role in BUILTIN_ROLE_LABELS:
        return BUILTIN_ROLE_LABELS[role]
    for item in cls.get("roles") or []:
        if item.get("id") == role:
            return item.get("name") or role
    return role or ""


def permissions_of(cls, user_id):
    """Tập quyền của user trong lớp. Giáo viên chủ nhiệm luôn đủ mọi quyền."""
    if not cls:
        return set()
    if cls.get("teacher_id") == user_id:
        return set(ALL_PERMISSIONS)
    member = member_of(cls, user_id)
    if not member:
        return set()
    role = member.get("role")
    if role in BUILTIN_ROLE_PERMS:
        return set(BUILTIN_ROLE_PERMS[role])
    for item in cls.get("roles") or []:
        if item.get("id") == role:
            return set(p for p in item.get("permissions") or [] if p in ALL_PERMISSIONS)
    return set()


def has_permission(cls, user_id, permission):
    return permission in permissions_of(cls, user_id)


def builtin_roles():
    """Danh mục vai trò có sẵn kèm quyền mặc định."""
    return [{
        "id": key,
        "name": BUILTIN_ROLE_LABELS[key],
        "permissions": list(BUILTIN_ROLE_PERMS[key]),
        "builtin": True,
    } for key in ("student", "vice_class_monitor", "class_monitor", "team_leader")]


def custom_roles(cls):
    return [{**r, "builtin": False} for r in cls.get("roles") or []]


def role_catalog(cls):
    """Danh mục quyền + vai trò có sẵn + vai trò tùy chỉnh của lớp."""
    return {
        "permissions": [{"id": key, "label": label} for key, label in PERMISSIONS.items()],
        "builtin": builtin_roles(),
        "custom": custom_roles(cls),
    }


def _require_owner(cls, actor_id):
    if not cls:
        return "Không tìm thấy lớp."
    if cls.get("teacher_id") != actor_id:
        return "Chỉ giáo viên chủ nhiệm mới thực hiện được."
    return None


def create_role(class_id, actor_id, name, permissions=None):
    cls = get_class(class_id)
    error = _require_owner(cls, actor_id)
    if error:
        return None, error
    name = (name or "").strip()
    if not name or len(name) > 40:
        return None, "Tên vai trò phải từ 1-40 ký tự."
    existing = [r.get("name", "").lower() for r in cls.get("roles") or []]
    existing += [label.lower() for label in BUILTIN_ROLE_LABELS.values()]
    if name.lower() in existing:
        return None, "Tên vai trò đã tồn tại."
    perms, error = _validate_permissions(permissions)
    if error:
        return None, error
    role = {"id": uuid.uuid4().hex[:8], "name": name, "permissions": perms,
            "created_at": _now()}
    cls.setdefault("roles", []).append(role)
    _save_class(cls)
    return role, None


def update_role(class_id, actor_id, role_id, name=None, permissions=None):
    cls = get_class(class_id)
    error = _require_owner(cls, actor_id)
    if error:
        return None, error
    role = next((r for r in cls.get("roles") or [] if r.get("id") == role_id), None)
    if not role:
        return None, "Không tìm thấy vai trò này."
    if name is not None:
        name = name.strip()
        if not name or len(name) > 40:
            return None, "Tên vai trò phải từ 1-40 ký tự."
        clash = [r.get("name", "").lower() for r in cls.get("roles") or []
                 if r.get("id") != role_id]
        clash += [label.lower() for label in BUILTIN_ROLE_LABELS.values()]
        if name.lower() in clash:
            return None, "Tên vai trò đã tồn tại."
        role["name"] = name
    if permissions is not None:
        perms, error = _validate_permissions(permissions)
        if error:
            return None, error
        role["permissions"] = perms
    role["updated_at"] = _now()
    _save_class(cls)
    return role, None


def delete_role(class_id, actor_id, role_id):
    cls = get_class(class_id)
    error = _require_owner(cls, actor_id)
    if error:
        return None, error
    roles = cls.get("roles") or []
    if not any(r.get("id") == role_id for r in roles):
        return None, "Không tìm thấy vai trò này."
    cls["roles"] = [r for r in roles if r.get("id") != role_id]
    reverted = 0
    for member in cls.get("members") or []:
        if member.get("role") == role_id:
            member["role"] = "student"
            reverted += 1
    _save_class(cls)
    return {"reverted": reverted}, None


# ---------------------------------------------------------------- quản lý lớp
def update_class(class_id, actor_id, name=None, grade=None):
    cls = get_class(class_id)
    error = _require_owner(cls, actor_id)
    if error:
        return None, error
    if name is not None:
        name = name.strip()
        if not name or len(name) > 60:
            return None, "Tên lớp phải từ 1-60 ký tự."
        cls["name"] = name
    if grade is not None:
        cls["grade"] = grade.strip()[:30]
    db.update("classes", {"name": cls["name"], "grade": cls.get("grade") or ""},
              [("id", class_id)])
    return cls, None


def regen_join_code(class_id, actor_id):
    cls = get_class(class_id)
    error = _require_owner(cls, actor_id)
    if error:
        return None, error
    code = _new_code()
    db.update("classes", {"join_code": code}, [("id", class_id)])
    cls["join_code"] = code
    return cls, None


def delete_class(class_id, actor_id):
    cls = get_class(class_id)
    error = _require_owner(cls, actor_id)
    if error:
        return None, error
    # Gỡ lớp khỏi các đề đã gán để không còn đề mồ côi được đăng công khai.
    for exam in exams_of_teacher(cls.get("teacher_id")):
        ids = [cid for cid in (exam.get("class_ids") or []) if cid != class_id]
        if ids != (exam.get("class_ids") or []):
            db.update("exams", {"class_ids": ids,
                                "published": exam.get("published") and bool(ids)},
                      [("id", exam["id"])])
    db.delete("classes", [("id", class_id)])
    return True, None


def class_with_names(cls):
    """Lớp kèm họ tên + email thành viên (cho UI)."""
    if not cls:
        return None
    out = dict(cls)
    ids = [m.get("user_id") for m in cls.get("members") or [] if m.get("user_id")]
    teacher_id = cls.get("teacher_id")
    if teacher_id:
        ids.append(teacher_id)
    accounts = {}
    if ids:
        try:
            accounts = {a["id"]: a for a in db.select("accounts", [("id", "in", ids)],
                                                     columns="id,name,email")}
        except db.SupabaseError:
            accounts = {}
    custom = {r.get("id"): r.get("name") for r in cls.get("roles") or []}
    out["members"] = [
        {**m, "name": accounts.get(m.get("user_id"), {}).get("name", "???"),
         "email": accounts.get(m.get("user_id"), {}).get("email", ""),
         "role_label": custom.get(m.get("role")) or role_label(cls, m.get("role"))}
        for m in cls.get("members") or []
    ]
    out["teacher_name"] = accounts.get(teacher_id, {}).get("name", "")
    out["roles"] = custom_roles(cls)
    return out


# ---------------------------------------------------------------- đề thi (portal)
def create_exam(created_by, title, duration_minutes=60, questions=None,
                source_text="", filename="", mode="shared", subject="", quiz_id=None):
    title = (title or "").strip()
    if not title or len(title) > 120:
        return None, "Tên đề thi phải từ 1-120 ký tự."
    exam = {
        "id": uuid.uuid4().hex[:10],
        "title": title,
        "subject": (subject or "").strip()[:60],
        "created_by": created_by,
        "quiz_id": quiz_id,
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
    db.insert("exams", exam)
    return exam, None


def get_exam(exam_id):
    if not exam_id:
        return None
    return db.select_one("exams", [("id", exam_id)])


def _save_exam(exam):
    db.update("exams", {
        "title": exam.get("title"),
        "subject": exam.get("subject"),
        "duration_minutes": exam.get("duration_minutes"),
        "questions": exam.get("questions") or [],
        "class_ids": exam.get("class_ids") or [],
        "published": bool(exam.get("published")),
        "start_at": exam.get("start_at"),
        "end_at": exam.get("end_at"),
    }, [("id", exam["id"])])


def exams_of_teacher(teacher_id):
    return db.select("exams", [("created_by", teacher_id)])


def exams_for_student(user_id, classes):
    """Đề đã xuất bản và được gán cho lớp mà học sinh đang ở trong."""
    class_ids = {c["id"] for c in classes}
    if not class_ids:
        return []
    return [e for e in db.select("exams", [("published", True)])
            if class_ids.intersection(e.get("class_ids") or [])]


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
    db.update("exams", {"class_ids": list(class_ids)}, [("id", exam_id)])
    exam["class_ids"] = list(class_ids)
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
    db.update("exams", {"published": bool(published)}, [("id", exam_id)])
    exam["published"] = bool(published)
    return exam, None


def set_schedule(exam_id, actor_id, start_at=None, end_at=None):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới đổi lịch được."
    db.update("exams", {"start_at": start_at or None, "end_at": end_at or None},
              [("id", exam_id)])
    exam["start_at"] = start_at or None
    exam["end_at"] = end_at or None
    return exam, None


def delete_exam(exam_id, actor_id):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới xóa được."
    db.delete("exams", [("id", exam_id)])
    return True, None


def replace_questions(exam_id, actor_id, questions):
    exam = get_exam(exam_id)
    if not exam:
        return None, "Không tìm thấy đề."
    if exam.get("created_by") != actor_id:
        return None, "Chỉ người tạo đề mới đổi câu hỏi được."
    db.update("exams", {"questions": questions or []}, [("id", exam_id)])
    exam["questions"] = questions or []
    return exam, None


# ---------------------------------------------------------------- kho bộ đề (nhiều môn)
def create_quiz(title, subject="", mode="shared", questions=None,
                source_text="", filename=""):
    title = (title or "").strip()
    if not title or len(title) > 120:
        return None, "Tên bộ đề phải từ 1-120 ký tự."
    if mode not in ("shared", "random"):
        return None, "Chế độ không hợp lệ (shared hoặc random)."
    quiz = {
        "id": uuid.uuid4().hex[:10],
        "title": title,
        "subject": (subject or "").strip()[:60],
        "mode": mode,
        "questions": questions or [],
        "source_text": source_text,
        "filename": filename,
        "created_at": _now(),
        "updated_at": None,
    }
    db.insert("quizzes", quiz)
    return quiz, None


def get_quiz(quiz_id):
    if not quiz_id:
        return None
    return db.select_one("quizzes", [("id", quiz_id)])


def list_quizzes():
    return db.select("quizzes", order="created_at.asc")


def update_quiz(quiz_id, **fields):
    quiz = get_quiz(quiz_id)
    if not quiz:
        return None, "Không tìm thấy bộ đề."
    allowed = {k: v for k, v in fields.items()
               if k in ("title", "subject", "mode", "questions", "source_text",
                        "filename", "updated_at")}
    if "questions" in allowed:
        allowed["updated_at"] = _now()
    if allowed:
        db.update("quizzes", allowed, [("id", quiz_id)])
        quiz.update(allowed)
    return quiz, None


def delete_quiz(quiz_id):
    quiz = get_quiz(quiz_id)
    if not quiz:
        return None, "Không tìm thấy bộ đề."
    db.delete("quizzes", [("id", quiz_id)])
    return True, None


# ---------------------------------------------------------------- phiên thi & bài nộp
def save_exam_session(session_id, name, start_time, questions, user_id, exam_id,
                      quiz_id=None):
    db.insert("exam_sessions", {
        "session_id": session_id,
        "name": name,
        "user_id": user_id,
        "exam_id": exam_id,
        "quiz_id": quiz_id,
        "start_time": start_time.isoformat(),
        "shuffled_questions": questions,
    })


def get_exam_session(session_id):
    if not session_id:
        return None
    return db.select_one("exam_sessions", [("session_id", session_id)])


def delete_exam_session(session_id):
    if session_id:
        db.delete("exam_sessions", [("session_id", session_id)])


def cleanup_old_sessions(max_age_hours=2):
    now = datetime.now(timezone.utc)
    for sess in db.select("exam_sessions", columns="session_id,start_time"):
        try:
            start = datetime.fromisoformat(sess["start_time"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            expired = (now - start).total_seconds() > max_age_hours * 3600
        except (ValueError, KeyError, TypeError):
            expired = True
        if expired:
            db.delete("exam_sessions", [("session_id", sess["session_id"])])


def save_attempt(attempt):
    db.insert("attempts", attempt)
    return attempt


def attempts_of_exam(exam_id):
    return db.select("attempts", [("exam_id", exam_id)])


def attempts_of_quiz(quiz_id):
    return db.select("attempts", [("quiz_id", quiz_id), ("source", "anonymous")])


def attempts_of_user(user_id):
    return db.select("attempts", [("user_id", user_id)])


def anonymous_attempts():
    return db.select("attempts", [("source", "anonymous")])


def attempts_by_name(name):
    return db.select("attempts", [("user_name", name), ("source", "anonymous")])


def has_attempt(exam_id, user_id):
    return db.select_one("attempts", [("exam_id", exam_id), ("user_id", user_id)]) is not None


def attempts_in_classes(exam_ids, member_ids):
    """Bài nộp của các thành viên trong các đề đã cho (dùng cho bảng điểm)."""
    if not exam_ids or not member_ids:
        return []
    return db.select("attempts", [("exam_id", "in", list(exam_ids)),
                                  ("user_id", "in", list(member_ids))])
