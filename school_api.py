"""API cho hệ thống quản lý lớp học & đề thi (theo vai trò).

Phân quyền:
  teacher       - giáo viên: tạo lớp/tổ, phân vai, tạo & gán đề, xem điểm
  student       - học sinh: vào lớp bằng mã, làm đề được gán, xem điểm của mình
  class_monitor - lớp trưởng: xem danh sách lớp + bảng điểm cả lớp
  team_leader   - tổ trưởng: xem bảng điểm của tổ mình
"""
import asyncio
import json
import random
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

import school_store as store

router = APIRouter(prefix="/api")


def _err(status, message):
    return JSONResponse(status_code=status, content={"error": message})


def _me(request):
    return store.user_from_token(request.cookies.get("sid"))


def _set_cookie(response, token):
    response.set_cookie("sid", token, httponly=True, samesite="lax",
                        max_age=store.SESSION_TTL_DAYS * 86400, path="/")
    return response


def _cls_with_role(cls, user):
    """Kèm vai trò + quyền của user trong lớp (nếu là thành viên)."""
    member = store.member_of(cls, user["id"]) if user else None
    out = store.class_with_names(cls)
    out["my_role"] = member.get("role") if member else None
    out["my_role_label"] = store.role_label(cls, member.get("role")) if member else None
    out["my_team_id"] = member.get("team_id") if member else None
    out["is_teacher"] = cls.get("teacher_id") == (user or {}).get("id")
    out["permissions"] = sorted(store.permissions_of(cls, (user or {}).get("id")))
    return out


def _public_exam(exam, include_questions=False):
    out = {
        "id": exam["id"],
        "title": exam.get("title"),
        "subject": exam.get("subject"),
        "quiz_id": exam.get("quiz_id"),
        "duration_minutes": exam.get("duration_minutes"),
        "question_count": len(exam.get("questions") or []),
        "class_ids": exam.get("class_ids") or [],
        "published": exam.get("published"),
        "start_at": exam.get("start_at"),
        "end_at": exam.get("end_at"),
        "filename": exam.get("filename"),
        "created_at": exam.get("created_at"),
        "created_by": exam.get("created_by"),
    }
    if include_questions:
        out["questions"] = [
            {k: v for k, v in q.items() if k != "correctText"}
            for q in exam.get("questions") or []
        ]
    return out


def _require_class_owner(request, class_id):
    """Trả về (user, None) nếu đúng quyền; ngược lại (None, response lỗi)."""
    user = _me(request)
    if not user:
        return None, _err(401, "Bạn chưa đăng nhập.")
    cls = store.get_class(class_id)
    if not cls:
        return None, _err(404, "Không tìm thấy lớp.")
    if cls.get("teacher_id") != user["id"]:
        return None, _err(403, "Chỉ giáo viên chủ nhiệm mới thực hiện được.")
    return user, None


def _require_class_permission(request, class_id, permission):
    """Trả về (user, cls, tập quyền) nếu có quyền; ngược lại (None, None, response lỗi).

    Giáo viên chủ nhiệm luôn có mọi quyền nên không cần trường hợp riêng.
    """
    user = _me(request)
    if not user:
        return None, None, _err(401, "Bạn chưa đăng nhập.")
    cls = store.get_class(class_id)
    if not cls:
        return None, None, _err(404, "Không tìm thấy lớp.")
    perms = store.permissions_of(cls, user["id"])
    if permission not in perms:
        return None, None, _err(403, "Bạn không có quyền này trong lớp: " +
                               store.PERMISSIONS.get(permission, permission))
    return user, cls, perms


def _require_exam_owner(request, exam_id):
    """Trả về (user, None) nếu đúng quyền; ngược lại (None, response lỗi)."""
    user = _me(request)
    if not user:
        return None, _err(401, "Bạn chưa đăng nhập.")
    exam = store.get_exam(exam_id)
    if not exam:
        return None, _err(404, "Không tìm thấy đề.")
    if exam.get("created_by") != user["id"]:
        return None, _err(403, "Chỉ người tạo đề mới thực hiện được.")
    return user, None


# ------------------------------------------------------------------ auth
@router.post("/auth/register")
async def register(request: Request, payload: dict):
    account, error = store.create_account(
        payload.get("email"), payload.get("name"), payload.get("role"),
        payload.get("password"),
    )
    if error:
        return _err(400, error)
    token = store.create_auth_session(account["id"])
    return _set_cookie(JSONResponse(status_code=201, content={"user": account}), token)


@router.post("/auth/login")
async def login(request: Request, payload: dict):
    account, error = store.login(payload.get("email"), payload.get("password"))
    if error:
        return _err(401, error)
    token = store.create_auth_session(account["id"])
    return _set_cookie(JSONResponse(content={"user": account}), token)


@router.post("/auth/logout")
async def logout(request: Request):
    store.destroy_auth_session(request.cookies.get("sid"))
    response = JSONResponse(content={"message": "ok"})
    response.delete_cookie("sid", path="/")
    return response


@router.get("/auth/me")
async def me(request: Request):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    return {"user": user}


# ------------------------------------------------------------------ lớp học
@router.get("/classes")
async def list_classes(request: Request):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    classes = (store.classes_of_teacher(user["id"]) if user["role"] == "teacher"
               else store.classes_of_student(user["id"]))
    return {"classes": [_cls_with_role(c, user) for c in classes]}


@router.post("/classes")
async def create_class(request: Request, payload: dict):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    if user["role"] != "teacher":
        return _err(403, "Chỉ giáo viên mới tạo được lớp.")
    cls, error = store.create_class(user["id"], payload.get("name"), payload.get("grade", ""))
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


@router.post("/classes/join")
async def join_class(request: Request, payload: dict):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    if user["role"] != "student":
        return _err(403, "Chỉ học sinh mới vào lớp được.")
    cls, error = store.join_class(payload.get("code"), user["id"])
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


@router.get("/classes/{class_id}")
async def class_detail(request: Request, class_id: str):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    cls = store.get_class(class_id)
    if not cls:
        return _err(404, "Không tìm thấy lớp.")
    if cls.get("teacher_id") != user["id"] and not store.member_of(cls, user["id"]):
        return _err(403, "Bạn không thuộc lớp này.")
    exams = [e for e in store.exams_of_teacher(cls.get("teacher_id"))
             if class_id in (e.get("class_ids") or [])]
    out = _cls_with_role(cls, user)
    out["exams"] = [_public_exam(e) for e in exams]
    return {"class": out}


@router.post("/classes/{class_id}/teams")
async def create_team(request: Request, class_id: str, payload: dict):
    user, cls, error = _require_class_permission(request, class_id, "manage_teams")
    if cls is None:
        return error
    team, error = store.add_team(class_id, payload.get("name"))
    if error:
        return _err(400, error)
    return {"team": team}


@router.delete("/classes/{class_id}/teams/{team_id}")
async def delete_team(request: Request, class_id: str, team_id: str):
    user, cls, error = _require_class_permission(request, class_id, "manage_teams")
    if cls is None:
        return error
    cls, error = store.remove_team(class_id, team_id)
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


@router.patch("/classes/{class_id}/members/{user_id}")
async def update_member(request: Request, class_id: str, user_id: str, payload: dict):
    user, cls, error = _require_class_permission(request, class_id, "assign_roles")
    if cls is None:
        return error
    role = payload.get("role")
    is_owner = cls.get("teacher_id") == user["id"]
    # Lớp trưởng / lớp phó chỉ do giáo viên chủ nhiệm tự cấp để tránh leo quyền.
    if role in store.MONITOR_ROLES and not is_owner:
        return _err(403, "Chỉ giáo viên chủ nhiệm mới cấp được vai trò lớp trưởng / lớp phó.")
    team_id = payload.get("team_id", "__absent__")
    if team_id == "__absent__":
        team_id = None
        apply_team = False
    else:
        apply_team = True
    cls, error = store.set_member(
        class_id, user_id,
        role=role if role is not None else None,
        team_id=team_id if apply_team else None,
    )
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


@router.delete("/classes/{class_id}/members/{user_id}")
async def delete_member(request: Request, class_id: str, user_id: str):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    cls, error = store.remove_member(class_id, user["id"], user_id)
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


# ------------------------------------------------------------------ vai trò & phân quyền
@router.get("/classes/{class_id}/roles")
async def class_roles(request: Request, class_id: str):
    """Danh mục quyền + vai trò có sẵn + vai trò tự tạo (chỉ người phân quyền được xem)."""
    user, cls, perms = _require_class_permission(request, class_id, "assign_roles")
    if cls is None:
        return perms
    return {"class_id": class_id, "permissions_of_me": sorted(perms),
            **store.role_catalog(cls)}


@router.post("/classes/{class_id}/roles")
async def create_custom_role(request: Request, class_id: str, payload: dict):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    role, error = store.create_role(class_id, user["id"], payload.get("name"),
                                    payload.get("permissions"))
    if error:
        return _err(400, error)
    return {"role": role}


@router.patch("/classes/{class_id}/roles/{role_id}")
async def update_custom_role(request: Request, class_id: str, role_id: str, payload: dict):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    if "name" in payload and "permissions" not in payload:
        role, error = store.update_role(class_id, user["id"], role_id, name=payload.get("name"))
    elif "permissions" in payload and "name" not in payload:
        role, error = store.update_role(class_id, user["id"], role_id,
                                        permissions=payload.get("permissions"))
    else:
        role, error = store.update_role(class_id, user["id"], role_id,
                                        name=payload.get("name"),
                                        permissions=payload.get("permissions"))
    if error:
        return _err(400, error)
    return {"role": role}


@router.delete("/classes/{class_id}/roles/{role_id}")
async def delete_custom_role(request: Request, class_id: str, role_id: str):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    result, error = store.delete_role(class_id, user["id"], role_id)
    if error:
        return _err(400, error)
    return {"message": "ok", **result}


# ------------------------------------------------------------------ quản lý lớp
@router.patch("/classes/{class_id}")
async def edit_class(request: Request, class_id: str, payload: dict):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    cls, error = store.update_class(
        class_id, user["id"],
        name=payload.get("name") if "name" in payload else None,
        grade=payload.get("grade") if "grade" in payload else None,
    )
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


@router.delete("/classes/{class_id}")
async def remove_class(request: Request, class_id: str):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    _, error = store.delete_class(class_id, user["id"])
    if error:
        return _err(400, error)
    return {"message": "ok"}


@router.post("/classes/{class_id}/regen-code")
async def regenerate_join_code(request: Request, class_id: str):
    user, error = _require_class_owner(request, class_id)
    if error:
        return error
    cls, error = store.regen_join_code(class_id, user["id"])
    if error:
        return _err(400, error)
    return {"class": _cls_with_role(cls, user)}


# ------------------------------------------------------------------ đề thi
@router.get("/exams")
async def list_exams(request: Request):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    if user["role"] == "teacher":
        exams = store.exams_of_teacher(user["id"])
        return {"exams": [_public_exam(e) for e in exams], "is_teacher": True}
    classes = store.classes_of_student(user["id"])
    exams = store.exams_for_student(user["id"], classes)
    result = []
    for e in exams:
        item = _public_exam(e)
        item["done"] = store.has_attempt(e["id"], user["id"])
        result.append(item)
    return {"exams": result, "is_teacher": False}


@router.post("/exams")
async def create_exam(request: Request, title: str = Form(""),
                      subject: str = Form(""),
                      duration_minutes: int = Form(60),
                      class_ids: str = Form(""),
                      quiz_id: str = Form(""),
                      file: UploadFile = File(None)):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    if user["role"] != "teacher":
        return _err(403, "Chỉ giáo viên mới tạo được đề.")
    from main import extract_text, generate_questions, AIError  # import muộn để tránh vòng lặp

    source_text = ""
    filename = ""
    questions = None

    # Ưu tiên dùng lại một bộ đề đã có trong kho chung (nhiều môn).
    if quiz_id.strip():
        quiz = store.get_quiz(quiz_id.strip())
        if not quiz:
            return _err(404, "Không tìm thấy bộ đề trong kho.")
        if not quiz.get("questions"):
            return _err(400, "Bộ đề này chưa có câu hỏi.")
        questions = quiz["questions"]
        source_text = quiz.get("source_text") or ""
        filename = quiz.get("filename") or ""
        subject = subject.strip() or (quiz.get("subject") or "")
        title = title.strip() or quiz.get("title") or "Đề thi"
    elif file is not None and file.filename:
        data = await file.read()
        if len(data) > 5 * 1024 * 1024:
            return _err(413, "File quá lớn (tối đa 5MB).")
        try:
            source_text = extract_text(file.filename, data)
        except ValueError as e:
            return _err(400, str(e))
        if len(source_text.strip()) < 200:
            return _err(400, "Không trích được nội dung đủ dài từ tài liệu (cần ít nhất 200 ký tự).")
        filename = file.filename
        try:
            questions = await asyncio.to_thread(generate_questions, source_text)
        except AIError as e:
            return _err(502, str(e))
    else:
        return _err(400, "Cần tải lên tài liệu hoặc chọn một bộ đề có sẵn trong kho.")

    exam, error = store.create_exam(
        user["id"], title, duration_minutes=duration_minutes,
        questions=questions, source_text=source_text, filename=filename,
        subject=subject, quiz_id=quiz_id.strip() or None,
    )
    if error:
        return _err(400, error)

    ids = [c for c in json.loads(class_ids) if c] if class_ids.strip() else []
    if ids:
        exam, error = store.assign_exam(exam["id"], user["id"], ids)
        if error:
            return _err(400, error)
    return {"exam": _public_exam(exam)}


@router.post("/exams/{exam_id}/regenerate")
async def regenerate_exam(request: Request, exam_id: str):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    from main import generate_questions, AIError

    exam = store.get_exam(exam_id)
    if not exam:
        return _err(404, "Không tìm thấy đề.")
    if exam.get("created_by") != user["id"]:
        return _err(403, "Chỉ người tạo đề mới sinh lại được.")
    if not exam.get("source_text"):
        return _err(400, "Đề này không có tài liệu nguồn để sinh lại.")
    try:
        questions = await asyncio.to_thread(generate_questions, exam["source_text"])
    except AIError as e:
        return _err(502, str(e))
    exam, error = store.replace_questions(exam_id, user["id"], questions)
    if error:
        return _err(400, error)
    return {"exam": _public_exam(exam)}


@router.patch("/exams/{exam_id}")
async def update_exam(request: Request, exam_id: str, payload: dict):
    user, error = _require_exam_owner(request, exam_id)
    if error:
        return error
    exam = store.get_exam(exam_id)
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title or len(title) > 120:
            return _err(400, "Tên đề phải từ 1-120 ký tự.")
        exam["title"] = title
    if "duration_minutes" in payload:
        try:
            exam["duration_minutes"] = max(1, int(payload.get("duration_minutes")))
        except (TypeError, ValueError):
            return _err(400, "Thời lượng không hợp lệ.")
    if "start_at" in payload:
        exam["start_at"] = payload.get("start_at") or None
    if "end_at" in payload:
        exam["end_at"] = payload.get("end_at") or None
    store._save_exam(exam)
    return {"exam": _public_exam(exam)}


@router.post("/exams/{exam_id}/assign")
async def assign(request: Request, exam_id: str, payload: dict):
    user, error = _require_exam_owner(request, exam_id)
    if error:
        return error
    exam, error = store.assign_exam(exam_id, user["id"], payload.get("class_ids"))
    if error:
        return _err(400, error)
    return {"exam": _public_exam(exam)}


@router.post("/exams/{exam_id}/publish")
async def publish(request: Request, exam_id: str, payload: dict):
    user, error = _require_exam_owner(request, exam_id)
    if error:
        return error
    exam, error = store.set_publish(exam_id, user["id"], bool(payload.get("published")))
    if error:
        return _err(400, error)
    return {"exam": _public_exam(exam)}


@router.delete("/exams/{exam_id}")
async def remove_exam(request: Request, exam_id: str):
    user, error = _require_exam_owner(request, exam_id)
    if error:
        return error
    _, error = store.delete_exam(exam_id, user["id"])
    if error:
        return _err(400, error)
    return {"message": "ok"}


@router.post("/exams/{exam_id}/start")
async def start_exam(request: Request, exam_id: str, payload: dict = None):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    if user["role"] != "student":
        return _err(403, "Chỉ học sinh mới làm bài được.")
    exam = store.get_exam(exam_id)
    if not exam:
        return _err(404, "Không tìm thấy đề.")
    if not exam.get("published"):
        return _err(403, "Giáo viên chưa mở đề này.")
    classes = store.classes_of_student(user["id"])
    if not set(exam.get("class_ids") or []).intersection(c["id"] for c in classes):
        return _err(403, "Bạn không thuộc lớp được gán đề này.")
    if store.has_attempt(exam_id, user["id"]):
        return _err(409, "Bạn đã nộp bài bài thi này rồi.")

    now = datetime.now(timezone.utc)
    for key, label in (("start_at", "chưa đến giờ"), ("end_at", "đã hết hạn")):
        raw = exam.get(key)
        if raw:
            try:
                limit = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if limit.tzinfo is None:
                limit = limit.replace(tzinfo=timezone.utc)
            if key == "start_at" and now < limit:
                return _err(403, f"Bài thi {label} (mở lúc {raw}).")
            if key == "end_at" and now > limit:
                return _err(403, f"Bài thi {label} (đóng lúc {raw}).")

    questions = [{**q, "options": list(q.get("options", []))}
                 for q in (exam.get("questions") or [])]
    if not questions:
        return _err(503, "Đề chưa có câu hỏi.")
    random.shuffle(questions)
    for q in questions:
        random.shuffle(q["options"])

    session_id = __import__("uuid").uuid4().hex
    store.save_exam_session(session_id, user["name"], now, questions, user["id"], exam_id)
    return {
        "session_id": session_id,
        "start_time": now.isoformat(),
        "duration_minutes": exam.get("duration_minutes") or 60,
        "title": exam.get("title"),
        "questions": [{k: v for k, v in q.items() if k != "correctText"} for q in questions],
    }


@router.post("/attempts/submit")
async def submit_attempt(request: Request, payload: dict):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    session_id = payload.get("session_id")
    answers = payload.get("answers")
    session = store.get_exam_session(session_id) if session_id else None
    if not session:
        return _err(400, "Phiên làm bài không tồn tại hoặc đã hết hạn.")
    if session.get("user_id") != user["id"]:
        return _err(403, "Phiên làm bài không thuộc về bạn.")
    exam_id = session.get("exam_id")
    exam = store.get_exam(exam_id)
    if not exam:
        return _err(404, "Đề thi không còn tồn tại.")
    shuffled = session.get("shuffled_questions") or []
    if not isinstance(answers, list) or len(answers) != len(shuffled) or len(shuffled) == 0:
        return _err(400, "Dữ liệu câu trả lời không hợp lệ!")

    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(session["start_time"])
    duration_sec = int((now - start).total_seconds())
    limit_sec = (exam.get("duration_minutes") or 60) * 60 + 30
    if duration_sec < 0 or duration_sec > limit_sec:
        store.delete_exam_session(session_id)
        return _err(400, "Đã hết thời gian làm bài.")

    score = sum(1 for i, q in enumerate(shuffled)
                if q.get("correctText") and answers[i] == q.get("correctText"))
    duration_fmt = f"{duration_sec // 60:02d}:{duration_sec % 60:02d}"
    attempt = {
        "id": __import__("uuid").uuid4().hex[:12],
        "exam_id": exam_id,
        "exam_title": exam.get("title"),
        "user_id": user["id"],
        "user_name": user["name"],
        "score": score,
        "total": len(shuffled),
        "duration_sec": duration_sec,
        "started_at": session["start_time"],
        "submitted_at": now.isoformat(),
        "answers": answers,
    }
    store.save_attempt(attempt)
    store.delete_exam_session(session_id)
    # Cùng định dạng với /submit để trang thi hiển thị modal kết quả & xem lại bài cũ
    return {
        "message": "success",
        "score": f"{score}/{len(shuffled)}",
        "score_num": score,
        "name": user["name"],
        "total_questions": len(shuffled),
        "duration_formatted": duration_fmt,
        "duration_sec": duration_sec,
        "details": [
            {
                "idx": i,
                "text": shuffled[i].get("text", ""),
                "imageUrl": shuffled[i].get("imageUrl", ""),
                "options": shuffled[i].get("options", []),
                "userAnswer": answers[i],
                "correctAnswer": shuffled[i].get("correctText", ""),
                "isCorrect": (answers[i] == shuffled[i].get("correctText", ""))
                if shuffled[i].get("correctText") else False,
            }
            for i in range(len(shuffled))
        ],
    }


# ------------------------------------------------------------------ điểm số
def _allowed_result_class(user, cls):
    """Trả về (phạm_vũ, ghi_chú, tập_quyền); phạm_vũ None nghĩa là không có quyền xem.

    - "teacher": giáo viên chủ nhiệm, xem toàn bộ.
    - "class_monitor": có quyền xem bảng điểm cả lớp.
    - "team_leader": chỉ xem được bảng điểm của tổ mình.
    """
    perms = store.permissions_of(cls, user["id"])
    if cls.get("teacher_id") == user["id"]:
        return "teacher", None, perms
    if "view_class_results" in perms:
        return "class_monitor", None, perms
    if "view_team_results" in perms:
        member = store.member_of(cls, user["id"])
        team_id = (member or {}).get("team_id")
        if not team_id:
            return None, None, perms
        team = next((t for t in cls.get("teams") or [] if t.get("id") == team_id), None)
        return "team_leader", f"Chỉ hiển thị tổ: {team.get('name') if team else '?'}", perms
    return None, None, perms


@router.get("/exams/{exam_id}/results")
async def exam_results(request: Request, exam_id: str):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    exam = store.get_exam(exam_id)
    if not exam:
        return _err(404, "Không tìm thấy đề.")
    if exam.get("created_by") != user["id"]:
        return _err(403, "Chỉ người tạo đề mới xem được.")
    attempts = sorted(store.attempts_of_exam(exam_id),
                      key=lambda a: (-a.get("score", 0), a.get("duration_sec", 0)))
    return {"exam": _public_exam(exam),
            "results": [{k: a[k] for k in ("user_id", "user_name", "score", "total",
                                           "duration_sec", "submitted_at")}
                        for a in attempts]}


@router.get("/classes/{class_id}/results")
async def class_results(request: Request, class_id: str):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    cls = store.get_class(class_id)
    if not cls:
        return _err(404, "Không tìm thấy lớp.")
    access, scope_note, perms = _allowed_result_class(user, cls)
    if not access:
        member = store.member_of(cls, user["id"])
        if member and "view_team_results" in perms:
            return _err(403, "Bạn chưa được xếp vào tổ nào nên chưa xem được bảng điểm tổ.")
        return _err(403, "Bạn không có quyền xem bảng điểm của lớp này.")

    member_ids = [m["user_id"] for m in cls.get("members") or []]
    if access == "team_leader":
        my = store.member_of(cls, user["id"])
        team_id = (my or {}).get("team_id")
        member_ids = [m["user_id"] for m in cls.get("members") or []
                      if m.get("team_id") == team_id]

    my_member = store.member_of(cls, user["id"])
    access_label = ("Giáo viên chủ nhiệm" if access == "teacher"
                    else store.role_label(cls, (my_member or {}).get("role")) or "Thành viên")

    exams = [e for e in store.exams_of_teacher(cls.get("teacher_id"))
             if class_id in (e.get("class_ids") or [])]
    attempts = store.attempts_in_classes([e["id"] for e in exams], member_ids)

    accounts = {a["id"]: a for a in store.all_accounts()}
    teams = {t["id"]: t.get("name") for t in cls.get("teams") or []}
    member_team = {m["user_id"]: m.get("team_id") for m in cls.get("members") or []}
    member_role = {m["user_id"]: m.get("role") for m in cls.get("members") or []}
    member_role_label = {m["user_id"]: store.role_label(cls, m.get("role"))
                         for m in cls.get("members") or []}

    rows = []
    for m_id in member_ids:
        acc = accounts.get(m_id, {})
        mine = [a for a in attempts if a.get("user_id") == m_id]
        best = max((a.get("score", 0) for a in mine), default=None)
        rows.append({
            "user_id": m_id,
            "name": acc.get("name", "???"),
            "role": member_role.get(m_id),
            "role_label": member_role_label.get(m_id) or "Học sinh",
            "team": teams.get(member_team.get(m_id)) or "-",
            "attempts": len(mine),
            "best_score": best,
        })
    rows.sort(key=lambda r: (-(r["best_score"] if r["best_score"] is not None else -1),
                             r["name"]))
    return {
        "class": {"id": cls["id"], "name": cls["name"], "grade": cls.get("grade")},
        "access": access,
        "access_label": access_label,
        "permissions": sorted(perms),
        "note": scope_note,
        "exams": [_public_exam(e) for e in exams],
        "attempts": [{k: a[k] for k in ("user_id", "user_name", "exam_title", "score",
                                        "total", "duration_sec", "submitted_at")}
                     for a in sorted(attempts, key=lambda x: x.get("submitted_at", ""),
                                     reverse=True)],
        "rows": rows,
    }


@router.get("/me/attempts")
async def my_attempts(request: Request):
    user = _me(request)
    if not user:
        return _err(401, "Bạn chưa đăng nhập.")
    attempts = sorted(store.attempts_of_user(user["id"]),
                      key=lambda a: a.get("submitted_at", ""), reverse=True)
    return {"attempts": [{k: a[k] for k in ("exam_id", "exam_title", "score", "total",
                                            "duration_sec", "submitted_at")}
                         for a in attempts]}
