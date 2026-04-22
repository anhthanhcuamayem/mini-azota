from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime
import json, os

app = FastAPI()
DATA_FILE = "history.json"

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/submit")
async def handle_submit(request: Request):
    try:
        data = await request.json()
        
        # Đọc dữ liệu cũ
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try: submissions = json.load(f)
                except: submissions = []

        # Tạo bản ghi mới
        new_entry = {
            "name": data.get("name", "Anonym"),
            "score": "Đã ghi nhận",
            "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y")
        }
        submissions.append(new_entry)

        # Ghi file
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(submissions, f, ensure_ascii=False, indent=4)

        return new_entry # Trả về để JS nhận được data.score hoặc data.time
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
@app.get("/admin-check-history")
async def view_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []
