from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta, timezone
import json
import os
import uuid

app = FastAPI()
DATA_FILE = "history.json"
SESSIONS_FILE = "sessions.json"  # Lưu thời gian bắt đầu của từng phiên
ACCESS_CODE = "group3laso1"
CORRECT_ANSWERS = {"q1": "Lazy learner", "q2": "Vanishing Gradient"}

def get_vn_time():
    """Trả về thời gian Việt Nam (GMT+7) dạng chuỗi"""
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).strftime("%H:%M:%S %d/%m/%Y")

def get_current_utc():
    """Lấy thời gian UTC hiện tại (có múi giờ)"""
    return datetime.now(timezone.utc)

def format_duration(seconds):
    """Định dạng giây thành mm:ss"""
    if seconds < 0:
        seconds = 0
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"

def save_session(session_id, name, start_time):
    """Lưu thông tin phiên làm bài"""
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
    """Lấy thông tin phiên làm bài"""
    if not os.path.exists(SESSIONS_FILE):
        return None
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        try:
            sessions = json.load(f)
            return sessions.get(session_id)
        except:
            return None

def delete_session(session_id):
    """Xóa phiên sau khi nộp bài"""
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
    """Bắt đầu làm bài: tạo phiên và ghi nhận thời gian bắt đầu từ server"""
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        code = data.get("code", "").strip()
        
        if not name or code != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Sai mã truy cập hoặc chưa nhập tên!"})
        
        # Tạo session ID duy nhất
        session_id = str(uuid.uuid4())
        start_time = get_current_utc()
        
        # Lưu phiên
        save_session(session_id, name, start_time)
        
        return {"session_id": session_id, "start_time": start_time.isoformat()}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/submit")
async def handle_submit(request: Request):
    try:
        data = await request.json()
        
        # Kiểm tra mã truy cập
        if str(data.get("code")).strip().lower() != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})
        
        # Lấy session_id
        session_id = data.get("session_id")
        if not session_id:
            return JSONResponse(status_code=400, content={"error": "Không tìm thấy phiên làm bài!"})
        
        # Lấy thông tin phiên
        session = get_session(session_id)
        if not session:
            return JSONResponse(status_code=400, content={"error": "Phiên làm bài đã hết hạn hoặc không tồn tại!"})
        
        # Kiểm tra đã trả lời hết câu chưa
        answers = data.get("answers", {})
        if not answers.get("q1") or not answers.get("q2"):
            return JSONResponse(status_code=400, content={"error": "Vui lòng trả lời tất cả câu hỏi!"})
        
        # Tính điểm
        score = 0
        if answers.get("q1") == CORRECT_ANSWERS["q1"]:
            score += 1
        if answers.get("q2") == CORRECT_ANSWERS["q2"]:
            score += 1
        
        # Tính thời gian làm bài (từ lúc bắt đầu đến lúc nộp)
        start_time = datetime.fromisoformat(session["start_time"])
        now = get_current_utc()
        duration_sec = int((now - start_time).total_seconds())
        duration_fmt = format_duration(duration_sec)
        
        # Đọc file lịch sử
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    submissions = json.load(f)
                except:
                    submissions = []
        
        # Lưu bài nộp mới
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
        
        # Xóa phiên sau khi nộp bài
        delete_session(session_id)
        
        return {"score": f"{score}/2", "message": "success"}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/leaderboard")
async def get_leaderboard():
    """Trả về top 3 người có điểm cao nhất (nếu bằng điểm thì ai làm nhanh hơn)"""
    if not os.path.exists(DATA_FILE):
        return []
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            submissions = json.load(f)
        except:
            return []
    
    # Sắp xếp: điểm giảm dần, thời gian tăng dần (ai nhanh hơn xếp trên)
    sorted_subs = sorted(submissions, key=lambda x: (-x["score"], x["duration_sec"]))
    top3 = sorted_subs[:3]
    
    # Chuẩn bị dữ liệu trả về
    result = []
    for item in top3:
        result.append({
            "name": item["name"],
            "score": item["score"],
            "duration_formatted": item["duration_formatted"]
        })
    return result

@app.get("/admin-check-history")
async def view_history():
    """Xem toàn bộ lịch sử bài nộp (đường dẫn admin)"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
