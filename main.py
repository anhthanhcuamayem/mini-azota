from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
import json
import os
import uuid

app = FastAPI()

# Phục vụ thư mục images
if not os.path.exists("images"):
    os.makedirs("images")
app.mount("/images", StaticFiles(directory="images"), name="images")

DATA_FILE = "history.json"
SESSIONS_FILE = "sessions.json"
ACCESS_CODE = "group3laso1"
EXAM_DURATION_MINUTES = 90

# ========== HÀM TIỆN ÍCH ==========
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
    sessions[session_id] = {"name": name, "start_time": start_time.isoformat()}
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

# ========== API ==========
@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/get-questions")
async def get_questions():
    """
    Đọc file questions.txt (7 dòng/câu):
        dòng1: nội dung câu hỏi
        dòng2: tên file ảnh (có thể rỗng)
        dòng3: đáp án A
        dòng4: đáp án B
        dòng5: đáp án C
        dòng6: đáp án D
        dòng7: đáp án đúng (A, B, C, D)
    Trả về danh sách câu hỏi (có cả đáp án đúng dạng text)
    """
    questions = []
    try:
        with open("questions.txt", "r", encoding="utf-8") as f:
            lines = [line.rstrip('\n') for line in f.readlines()]
        # Mỗi câu 7 dòng
        for i in range(0, len(lines), 7):
            if i+6 >= len(lines):
                break
            text = lines[i]
            img_file = lines[i+1]
            optA = lines[i+2]
            optB = lines[i+3]
            optC = lines[i+4]
            optD = lines[i+5]
            correct_letter = lines[i+6].strip().upper()  # 'A', 'B', 'C', 'D'
            options = [optA, optB, optC, optD]
            # Xác định đáp án đúng theo text
            correct_text = ""
            if correct_letter == 'A':
                correct_text = optA
            elif correct_letter == 'B':
                correct_text = optB
            elif correct_letter == 'C':
                correct_text = optC
            elif correct_letter == 'D':
                correct_text = optD
            else:
                correct_text = ""  # fallback
            questions.append({
                "text": text,
                "imageUrl": f"/images/{img_file}" if img_file else "",
                "options": options,
                "correctText": correct_text
            })
        # Đảm bảo có ít nhất 40 câu (nếu file thiếu, thêm placeholder)
        while len(questions) < 40:
            questions.append({
                "text": "Câu hỏi đang được cập nhật",
                "imageUrl": "",
                "options": ["A. Đang cập nhật", "B. Đang cập nhật", "C. Đang cập nhật", "D. Đang cập nhật"],
                "correctText": "A. Đang cập nhật"
            })
        return questions[:40]
    except Exception as e:
        # Fallback nếu không đọc được file
        default = []
        for i in range(40):
            default.append({
                "text": f"Câu hỏi mặc định {i+1}",
                "imageUrl": "",
                "options": ["A", "B", "C", "D"],
                "correctText": "A"
            })
        return default

@app.post("/start")
async def start_exam(request: Request):
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        code = data.get("code", "").strip()
        if not name:
            return JSONResponse(status_code=400, content={"error": "Vui lòng nhập họ tên!"})
        if len(name) > 50:
            return JSONResponse(status_code=400, content={"error": "Tên không được quá 50 ký tự!"})
        if any(ord(c) < 32 or ord(c) == 127 for c in name):
            return JSONResponse(status_code=400, content={"error": "Tên chứa ký tự không hợp lệ!"})
        if code != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Sai mã truy cập!"})
        cleanup_old_sessions()
        session_id = str(uuid.uuid4())
        start_time = get_current_utc()
        save_session(session_id, name, start_time)
        return {
            "session_id": session_id,
            "start_time": start_time.isoformat(),
            "duration_minutes": EXAM_DURATION_MINUTES
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
        
        # Nhận mảng câu trả lời của 40 câu
        user_answers = data.get("answers", [])  # list of strings, length = 40
        if len(user_answers) != 40:
            return JSONResponse(status_code=400, content={"error": "Dữ liệu câu trả lời không hợp lệ!"})
        
        # Lấy danh sách câu hỏi (để biết đáp án đúng)
        questions = await get_questions()
        if len(questions) != 40:
            questions = questions[:40]
            while len(questions) < 40:
                questions.append({"correctText": ""})
        
        # Tính điểm
        score = 0
        for i in range(40):
            if user_answers[i] and user_answers[i] == questions[i]["correctText"]:
                score += 1
        
        start_time = datetime.fromisoformat(session["start_time"])
        now = get_current_utc()
        duration_sec = int((now - start_time).total_seconds())
        duration_fmt = format_duration(duration_sec)
        
        new_entry = {
            "name": session["name"],
            "score": score,
            "score_display": f"{score}/40",
            "duration_sec": duration_sec,
            "duration_formatted": duration_fmt,
            "submitted_at_display": get_vn_time(),
            "submitted_at_iso": now.isoformat(),
            "answers": user_answers  # lưu lại mảng đáp án
        }
        save_submission(new_entry)
        delete_session(session_id)
        
        return {
            "score": f"{score}/40",
            "message": "success",
            "name": session["name"],
            "total_questions": 40
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/leaderboard")
async def get_leaderboard():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    # Gom nhóm theo tên, lấy thành tích tốt nhất
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
    return {"leaderboard": top3, "total_questions": 40}

@app.get("/history/{name}")
async def get_user_history(name: str):
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    user_history = [s for s in submissions if s["name"] == name]
    user_history.sort(key=lambda x: x.get("submitted_at_iso", ""), reverse=True)
    # Xóa answers để nhẹ
    for item in user_history:
        item.pop("answers", None)
    return user_history

@app.get("/admin-check-history")
async def view_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
