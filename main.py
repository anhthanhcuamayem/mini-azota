from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime
import json
import os

app = FastAPI()

ACCESS_CODE = "MaiHuyenDepGai"
MAX_USERS = 6
DATA_FILE = "history.json" # Tên file sẽ lưu dữ liệu

# Hàm đọc dữ liệu từ file
def read_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []

# Hàm ghi dữ liệu vào file
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

    if len(submissions) >= MAX_USERS:
        return JSONResponse(status_code=403, content={"error": "Hệ thống đã nhận đủ bài."})

    if data.get("code") != ACCESS_CODE:
        return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})

    name = data.get("name")
    # Kiểm tra xem tên này đã nộp chưa để tránh nộp trùng
    for s in submissions:
        if s['name'] == name:
            return JSONResponse(status_code=400, content={"error": "Bạn đã nộp bài trước đó rồi!"})

    ans = data.get("answers", {})
    start_time = datetime.fromisoformat(data.get("start_time"))
    end_time = datetime.now()
    
    # Chấm điểm
    score = 0
    if ans.get("1") == "Lazy learner": score += 1
    if ans.get("2") == "Vanishing Gradient": score += 1

    new_submission = {
        "name": name,
        "score": f"{score}/2",
        "duration": str(end_time - start_time).split(".")[0],
        "time": end_time.strftime("%H:%M:%S %d/%m/%Y")
    }
    
    submissions.append(new_submission)
    save_data(submissions) # Lưu lại vào file
    return new_submission

@app.get("/admin-check-history")
async def view_history():
    return read_data()
