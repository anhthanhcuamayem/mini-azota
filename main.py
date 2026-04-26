from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
import json
import os

app = FastAPI()
DATA_FILE = "history.json"
ACCESS_CODE = "group3laso1"
CORRECT_ANSWERS = ["Lazy learner", "Vanishing Gradient"]   # for question 1 and 2

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
        # Check access code
        if str(data.get("code")).strip().lower() != ACCESS_CODE:
            return JSONResponse(status_code=401, content={"error": "Mã truy cập sai!"})

        # Load existing submissions
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    submissions = json.load(f)
                except:
                    submissions = []

        # Compute score: support both old format (answers dict) and new format (answers_array)
        score = 0
        answers_array = data.get("answers_array")
        if answers_array is not None and isinstance(answers_array, list):
            # New format: array of 40 answers (null for unanswered)
            if len(answers_array) >= 2:
                if answers_array[0] == CORRECT_ANSWERS[0]:
                    score += 1
                if answers_array[1] == CORRECT_ANSWERS[1]:
                    score += 1
        else:
            # Legacy support
            ans = data.get("answers", {})
            if ans.get("q1") == CORRECT_ANSWERS[0]:
                score += 1
            if ans.get("q2") == CORRECT_ANSWERS[1]:
                score += 1

        # Save result
        new_entry = {
            "name": data.get("name", "Ẩn danh"),
            "score": f"{score}/2",
            "time": get_vn_time(),
            "answers_array": answers_array if answers_array else [],
            "legacy_details": data.get("answers", {})
        }
        submissions.append(new_entry)

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(submissions, f, ensure_ascii=False, indent=4)

        return {"score": f"{score}/2", "message": "success"}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/admin-check-history")
async def view_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
