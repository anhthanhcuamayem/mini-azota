from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import os

app = FastAPI()

# Cấu hình
ACCESS_CODE = "12A2" # Mã vào thi, bạn có thể đổi
MAX_USERS = 6
db_submissions = []

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/submit")
async def handle_submit(data: dict):
    if len(db_submissions) >= MAX_USERS:
        return JSONResponse(status_code=403, content={"error": "Hệ thống đã nhận đủ 6 người."})

    if data.get("code") != ACCESS_CODE:
        return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})

    name = data.get("name")
    ans = data.get("answers", {})
    start_time = datetime.fromisoformat(data.get("start_time"))
    end_time = datetime.now()
    
    # Logic chấm điểm mẫu (Bạn có thể sửa câu hỏi/đáp án ở đây)
    score = 0
    if ans.get("1") == "Lazy learner": score += 1
    if ans.get("2") == "Vanishing Gradient": score += 1

    submission = {
        "name": name,
        "score": f"{score}/2",
        "duration": str(end_time - start_time).split(".")[0],
        "time": end_time.strftime("%H:%M:%S")
    }
    db_submissions.append(submission)
    return submission

@app.get("/admin-check-history")
async def view_history():
    return db_submissions
