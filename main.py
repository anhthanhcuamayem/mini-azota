from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime
import json
import os

app = FastAPI()

# Cấu hình hệ thống
ACCESS_CODE = "group3laso1"
MAX_USERS = 6
DATA_FILE = "history.json"

# Hàm đọc dữ liệu từ file lưu trữ
def read_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []

# Hàm ghi dữ liệu vào file lưu trữ
def save_data(data_list):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/submit")
async def handle_submit(data: dict):
    submissions = read_data()
    
    # Kiểm tra số lượng người nộp
    if len(submissions) >= MAX_USERS:
        return JSONResponse(status_code=403, content={"error": "Hệ thống đã nhận đủ 6 người."})

    # Kiểm tra mã truy cập (xóa khoảng trắng và không phân biệt hoa thường)
    user_code = str(data.get("code", "")).strip().lower()
    if user_code != ACCESS_CODE.lower():
        return JSONResponse(status_code=401, content={"error": "Mã truy cập không đúng!"})

    name = data.get("name")
    ans = data.get("answers", {})
    start_time_str = data.get("start_time")
    
    # Tính điểm
    score = 0
    if ans.get("1") == "Lazy learner": score += 1
    if ans.get("2") == "Vanishing Gradient": score += 1

    # Tính thời gian làm bài
    start_time = datetime.fromisoformat(start_time_str)
    end_time = datetime.now()
    duration = str(end_time - start_time).split(".")[0]

    new_submission = {
        "name": name,
        "score": f"{score}/2",
        "duration": duration,
        "time": end_time.strftime("%H:%M:%S %d/%m/%Y")
    }
    
    submissions.append(new_submission)
    save_data(submissions)
    return new_submission

@app.get("/admin-check-history")
async def view_history():
    return read_data()
