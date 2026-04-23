from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
import json
import os

app = FastAPI()
DATA_FILE = "history.json"
ACCESS_CODE = "group3laso1"

# Hàm lấy giờ Việt Nam (GMT+7)
def get_vn_time():
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%H:%M:%S %d/%m/%Y")

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/submit")
async def handle_submit(request: Request):
    try:
        data = await request.json()
        
        # 1. Kiểm tra mã truy cập
        if str(data.get("code")).strip().lower() != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})

        # 2. Đọc dữ liệu cũ từ file json
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    submissions = json.load(f)
                except:
                    submissions = []

        # 3. Tính điểm (Dựa trên chữ của đáp án)
        ans = data.get("answers", {})
        score = 0
        if ans.get("q1") == "Lazy learner": score += 1
        if ans.get("q2") == "Vanishing Gradient": score += 1

        # 4. Lưu kết quả mới
        new_entry = {
            "name": data.get("name", "Ẩn danh"),
            "score": f"{score}/2",
            "time": get_vn_time(),
            "details": ans
        }
        submissions.append(new_entry)

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(submissions, f, ensure_ascii=False, indent=4)

        return new_entry

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# Đường dẫn xem điểm: https://tên-web.onrender.com/admin-check-history
@app.get("/admin-check-history")
async def view_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []