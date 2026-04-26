from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta, timezone
import json
import os

app = FastAPI()
DATA_FILE = "history.json"
ACCESS_CODE = "group3laso1"
CORRECT_ANSWERS = {"q1": "Lazy learner", "q2": "Vanishing Gradient"}

def get_vn_time():
    """Trả về thời gian Việt Nam (GMT+7) dạng chuỗi"""
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).strftime("%H:%M:%S %d/%m/%Y")

def compute_duration(start_iso_str):
    """
    Tính số giây từ start_time đến thời điểm hiện tại.
    Xử lý cả trường hợp start_time có hoặc không có múi giờ.
    """
    if not start_iso_str:
        return 999999
    
    # Chuyển đổi start_time từ chuỗi ISO sang datetime
    # Thay thế 'Z' bằng '+00:00' nếu có
    start_str = start_iso_str.replace('Z', '+00:00')
    
    try:
        start = datetime.fromisoformat(start_str)
    except:
        # Nếu parse lỗi, trả về thời gian lớn
        return 999999
    
    # Lấy thời gian hiện tại theo UTC (có múi giờ)
    now = datetime.now(timezone.utc)
    
    # Nếu start không có múi giờ, gán nó là UTC
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    
    # Tính chênh lệch
    diff = now - start
    return int(diff.total_seconds())

def format_duration(seconds):
    """Định dạng giây thành mm:ss"""
    if seconds >= 999999:
        return "Chưa rõ"
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
        
        # Kiểm tra mã truy cập
        if str(data.get("code")).strip().lower() != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})
        
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
        
        # Lưu bài nộp mới
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
