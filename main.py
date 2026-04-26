from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta, timezone
import json
import os
import uuid

app = FastAPI()
DATA_FILE = "history.json"
SESSIONS_FILE = "sessions.json"
ACCESS_CODE = "group3laso1"
CORRECT_ANSWERS = {"q1": "Lazy learner", "q2": "Vanishing Gradient"}

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
    
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=4)

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
    
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=4)

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
        
        if not name or code != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Sai mã truy cập hoặc chưa nhập tên!"})
        
        session_id = str(uuid.uuid4())
        start_time = get_current_utc()
        
        save_session(session_id, name, start_time)
        
        return {"session_id": session_id, "start_time": start_time.isoformat()}
    
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
        
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    submissions = json.load(f)
                except:
                    submissions = []
        
        new_entry = {
            "name": session["name"],
            "score": score,
            "score_display": f"{score}/2",
            "duration_sec": duration_sec,
            "duration_formatted": duration_fmt,
            "submitted_at": get_vn_time(),
            "answers": answers
        }
        submissions.append(new_entry)
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(submissions, f, ensure_ascii=False, indent=4)
        
        delete_session(session_id)
        
        return {"score": f"{score}/2", "message": "success", "name": session["name"]}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/leaderboard")
async def get_leaderboard():
    """Trả về top 3 người có thành tích CAO NHẤT (nếu trùng tên thì lấy điểm cao nhất, thời gian nhanh nhất)"""
    if not os.path.exists(DATA_FILE):
        return []
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    
    # Gom nhóm theo tên, lấy thành tích tốt nhất của mỗi người
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
            # Nếu điểm cao hơn, hoặc bằng điểm nhưng thời gian nhanh hơn
            current = best_by_name[name]
            if score > current["score"] or (score == current["score"] and duration < current["duration_sec"]):
                best_by_name[name] = {
                    "name": name,
                    "score": score,
                    "duration_sec": duration,
                    "duration_formatted": sub["duration_formatted"]
                }
    
    # Chuyển thành list và sắp xếp
    best_list = list(best_by_name.values())
    sorted_subs = sorted(best_list, key=lambda x: (-x["score"], x["duration_sec"]))
    top3 = sorted_subs[:3]
    
    return top3

@app.get("/history/{name}")
async def get_user_history(name: str):
    """Lấy lịch sử làm bài của một người cụ thể"""
    if not os.path.exists(DATA_FILE):
        return []
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    
    # Lọc theo tên, sắp xếp theo thời gian mới nhất trước
    user_history = [s for s in submissions if s["name"] == name]
    user_history.sort(key=lambda x: x["submitted_at"], reverse=True)
    
    return user_history

@app.get("/admin-check-history")
async def view_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
