from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta
import json
import os

app = FastAPI()
DATA_FILE = "history.json"
ACCESS_CODE = "group3laso1"
CORRECT_ANSWERS = {"q1": "Lazy learner", "q2": "Vanishing Gradient"}

def get_vn_time():
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%H:%M:%S %d/%m/%Y")

def compute_duration(start_iso_str):
    """Tính số giây từ start_time đến hiện tại"""
    if not start_iso_str:
        return 999999
    start = datetime.fromisoformat(start_iso_str)
    now = datetime.utcnow()
    return int((now - start).total_seconds())

def format_duration(seconds):
    """mm:ss"""
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/submit")
async def handle_submit(request: Request):
    try:
        data = await request.json()
        # Check mã
        if str(data.get("code")).strip().lower() != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})
        
        # Kiểm tra đã trả lời hết câu chưa (phía client đã kiểm tra, nhưng server cũng kiểm tra an toàn)
        answers = data.get("answers", {})
        if not answers.get("q1") or not answers.get("q2"):
            return JSONResponse(status_code=400, content={"error": "Vui lòng trả lời tất cả câu hỏi!"})
        
        # Tính điểm
        score = 0
        if answers.get("q1") == CORRECT_ANSWERS["q1"]:
            score += 1
        if answers.get("q2") == CORRECT_ANSWERS["q2"]:
            score += 1
        
        # Tính thời gian làm bài
        start_time_str = data.get("start_time")
        duration_sec = compute_duration(start_time_str)
        duration_fmt = format_duration(duration_sec)
        
        # Đọc file lịch sử
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    submissions = json.load(f)
                except:
                    submissions = []
        
        # Lưu bài nộp
        new_entry = {
            "name": data.get("name", "Ẩn danh"),
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
    
    # Sắp xếp: điểm giảm dần, thời gian tăng dần
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
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
