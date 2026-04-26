from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta, timezone
import json
import os
import uuid
import re

app = FastAPI()
DATA_FILE = "history.json"
SESSIONS_FILE = "sessions.json"
ACCESS_CODE = "group3laso1"
EXAM_DURATION_MINUTES = 90
CORRECT_ANSWERS = {"q1": "Lazy learner", "q2": "Vanishing Gradient"}
TOTAL_QUESTIONS = 2  # chỉ 2 câu tính điểm, các câu còn lại là placeholder

def get_vn_time():
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).strftime("%H:%M:%S %d/%m/%Y")

def get_current_utc():
    return datetime.now(timezone.utc)

def format_duration(seconds):
    if seconds < 0:
        seconds = 0
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"

def save_session(session_id, name, start_time):
    sessions = {}
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            try:
                sessions = json.load(f)
            except:
                sessions = {}
    
    sessions[session_id] = {
        "name": name,
        "start_time": start_time.isoformat()
    }
    
    # atomic write
    with open(SESSIONS_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=4)
    os.replace(SESSIONS_FILE + ".tmp", SESSIONS_FILE)

def get_session(session_id):
    if not os.path.exists(SESSIONS_FILE):
        return None
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        try:
            sessions = json.load(f)
            return sessions.get(session_id)
        except:
            return None

def delete_session(session_id):
    if not os.path.exists(SESSIONS_FILE):
        return
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        try:
            sessions = json.load(f)
        except:
            sessions = {}
    
    if session_id in sessions:
        del sessions[session_id]
    
    with open(SESSIONS_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=4)
    os.replace(SESSIONS_FILE + ".tmp", SESSIONS_FILE)

def cleanup_old_sessions(max_age_hours=2):
    """Xóa session cũ hơn max_age_hours"""
    if not os.path.exists(SESSIONS_FILE):
        return
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        try:
            sessions = json.load(f)
        except:
            sessions = {}
    
    now = get_current_utc()
    expired = []
    for sid, data in sessions.items():
        try:
            start = datetime.fromisoformat(data["start_time"])
            if (now - start).total_seconds() > max_age_hours * 3600:
                expired.append(sid)
        except:
            expired.append(sid)
    
    if expired:
        for sid in expired:
            del sessions[sid]
        with open(SESSIONS_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=4)
        os.replace(SESSIONS_FILE + ".tmp", SESSIONS_FILE)

def save_submission(entry):
    """Ghi submission một cách atomic"""
    submissions = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                submissions = json.load(f)
            except:
                submissions = []
    submissions.append(entry)
    with open(DATA_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(submissions, f, ensure_ascii=False, indent=4)
    os.replace(DATA_FILE + ".tmp", DATA_FILE)

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/start")
async def start_exam(request: Request):
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        code = data.get("code", "").strip()
        
        # Validation
        if not name or code != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Sai mã truy cập hoặc chưa nhập tên!"})
        if len(name) > 50 or not re.match(r'^[\p{L}\p{N}\s]+$', name, re.UNICODE):
            return JSONResponse(status_code=400, content={"error": "Tên không hợp lệ (chỉ chữ, số, khoảng trắng, tối đa 50 ký tự)!"})
        
        # Dọn dẹp session cũ
        cleanup_old_sessions()
        
        session_id = str(uuid.uuid4())
        start_time = get_current_utc()
        
        save_session(session_id, name, start_time)
        
        return {
            "session_id": session_id,
            "start_time": start_time.isoformat(),
            "duration_minutes": EXAM_DURATION_MINUTES,
            "total_questions": TOTAL_QUESTIONS
        }
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/submit")
async def handle_submit(request: Request):
    try:
        data = await request.json()
        
        if str(data.get("code")).strip().lower() != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})
        
        session_id = data.get("session_id")
        if not session_id:
            return JSONResponse(status_code=400, content={"error": "Không tìm thấy phiên làm bài!"})
        
        session = get_session(session_id)
        if not session:
            return JSONResponse(status_code=400, content={"error": "Phiên làm bài đã hết hạn hoặc không tồn tại!"})
        
        answers = data.get("answers", {})
        if not answers.get("q1") or not answers.get("q2"):
            return JSONResponse(status_code=400, content={"error": "Vui lòng trả lời tất cả câu hỏi!"})
        
        score = 0
        if answers.get("q1") == CORRECT_ANSWERS["q1"]:
            score += 1
        if answers.get("q2") == CORRECT_ANSWERS["q2"]:
            score += 1
        
        start_time = datetime.fromisoformat(session["start_time"])
        now = get_current_utc()
        duration_sec = int((now - start_time).total_seconds())
        duration_fmt = format_duration(duration_sec)
        
        new_entry = {
            "name": session["name"],
            "score": score,
            "score_display": f"{score}/{TOTAL_QUESTIONS}",
            "duration_sec": duration_sec,
            "duration_formatted": duration_fmt,
            "submitted_at_display": get_vn_time(),
            "submitted_at_iso": now.isoformat(),
            "answers": answers
        }
        save_submission(new_entry)
        
        delete_session(session_id)
        
        return {
            "score": f"{score}/{TOTAL_QUESTIONS}",
            "message": "success",
            "name": session["name"],
            "total_questions": TOTAL_QUESTIONS
        }
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/leaderboard")
async def get_leaderboard():
    """Trả về top 3 người có thành tích CAO NHẤT (mỗi người lấy điểm cao nhất, thời gian nhanh nhất)"""
    if not os.path.exists(DATA_FILE):
        return []
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    
    best_by_name = {}
    for sub in submissions:
        name = sub["name"]
        score = sub["score"]
        duration = sub["duration_sec"]
        
        if name not in best_by_name:
            best_by_name[name] = {
                "name": name,
                "score": score,
                "duration_sec": duration,
                "duration_formatted": sub["duration_formatted"]
            }
        else:
            current = best_by_name[name]
            if score > current["score"] or (score == current["score"] and duration < current["duration_sec"]):
                best_by_name[name] = {
                    "name": name,
                    "score": score,
                    "duration_sec": duration,
                    "duration_formatted": sub["duration_formatted"]
                }
    
    best_list = list(best_by_name.values())
    sorted_subs = sorted(best_list, key=lambda x: (-x["score"], x["duration_sec"]))
    top3 = sorted_subs[:3]
    
    # Thêm total_questions cho FE
    return {"leaderboard": top3, "total_questions": TOTAL_QUESTIONS}

@app.get("/history/{name}")
async def get_user_history(name: str):
    """Lấy lịch sử làm bài, sắp xếp theo thời gian mới nhất trước (dùng ISO)"""
    if not os.path.exists(DATA_FILE):
        return []
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    
    user_history = [s for s in submissions if s["name"] == name]
    # Sắp xếp theo submitted_at_iso giảm dần (mới nhất lên đầu)
    user_history.sort(key=lambda x: x.get("submitted_at_iso", ""), reverse=True)
    
    # Loại bỏ trường answers nếu không muốn gửi lên (tiết kiệm bandwidth)
    for item in user_history:
        item.pop("answers", None)
    
    return user_history

@app.get("/admin-check-history")
async def view_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
