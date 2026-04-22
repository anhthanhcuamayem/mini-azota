from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta
import json, os
import random

app = FastAPI()
DATA_FILE = "history.json"

# Dữ liệu câu hỏi mẫu - Bạn có thể thêm nhiều câu hỏi hơn
QUESTIONS = {
    "part1": {  # Điền vào ô trống trong đoạn văn
        "title": "PHẦN 1: Điền từ vào chỗ trống",
        "image": "https://via.placeholder.com/600x200?text=Đoạn+văn+điền+từ",  # Thay bằng URL ảnh của bạn
        "questions": [
            {
                "id": 1,
                "text": "The children were playing ______ in the park.",
                "options": ["happy", "happily", "happiness", "unhappy"],
                "correct": "happily"
            },
            {
                "id": 2,
                "text": "She ______ to the market yesterday morning.",
                "options": ["go", "goes", "went", "going"],
                "correct": "went"
            },
            {
                "id": 3,
                "text": "If it rains tomorrow, we ______ the trip.",
                "options": ["cancel", "cancelled", "will cancel", "would cancel"],
                "correct": "will cancel"
            },
            {
                "id": 4,
                "text": "This is the book ______ I bought last week.",
                "options": ["who", "whom", "which", "what"],
                "correct": "which"
            },
            {
                "id": 5,
                "text": "She sings ______ than her sister.",
                "options": ["beautiful", "more beautiful", "beautifully", "more beautifully"],
                "correct": "more beautifully"
            }
        ]
    },
    "part2": {  # Chọn thứ tự câu
        "title": "PHẦN 2: Sắp xếp câu thành đoạn văn hoàn chỉnh",
        "image": "https://via.placeholder.com/600x200?text=Đoạn+văn+sắp+xếp+câu",
        "questions": [
            {
                "id": 6,
                "text": "Sắp xếp các câu sau thành đoạn văn hoàn chỉnh:",
                "sentences": [
                    "A. Finally, they reached the top and enjoyed the beautiful view.",
                    "B. First, they packed their bags and prepared everything needed.",
                    "C. The group started their journey early in the morning.",
                    "D. Then, they began climbing the mountain step by step."
                ],
                "correct_order": ["C", "B", "D", "A"],
                "type": "ordering"
            }
        ]
    },
    "part3": {  # Điền câu vào đoạn văn
        "title": "PHẦN 3: Chọn câu phù hợp điền vào đoạn văn",
        "image": "https://via.placeholder.com/600x200?text=Đoạn+văn+điền+câu",
        "questions": [
            {
                "id": 7,
                "text": "Chọn câu phù hợp để điền vào chỗ trống trong đoạn văn:",
                "paragraph": "Reading books is a wonderful habit. _______________. It also helps improve vocabulary and writing skills.",
                "options": [
                    "A. It makes us physically strong",
                    "B. It helps us relax and gain knowledge",
                    "C. It wastes our valuable time",
                    "D. It is very expensive to buy books"
                ],
                "correct": "B",
                "type": "insert_sentence"
            }
        ]
    },
    "part4": {  # Đọc và trả lời câu hỏi
        "title": "PHẦN 4: Đọc đoạn văn và trả lời câu hỏi",
        "image": "https://via.placeholder.com/600x300?text=Đoạn+văn+đọc+hiểu",
        "questions": [
            {
                "id": 8,
                "text": "According to the passage, what is the main benefit of regular exercise?",
                "options": [
                    "A. Losing weight quickly",
                    "B. Improving heart health and reducing stress",
                    "C. Building big muscles",
                    "D. Sleeping less"
                ],
                "correct": "B"
            },
            {
                "id": 9,
                "text": "How many minutes of exercise are recommended per week?",
                "options": [
                    "A. 30 minutes",
                    "B. 60 minutes",
                    "C. 150 minutes",
                    "D. 300 minutes"
                ],
                "correct": "C"
            },
            {
                "id": 10,
                "text": "What type of exercise is mentioned as beneficial for older adults?",
                "options": [
                    "A. Weight lifting",
                    "B. High-intensity running",
                    "C. Walking and swimming",
                    "D. Extreme sports"
                ],
                "correct": "C"
            }
        ]
    }
}

def shuffle_questions_and_options():
    """Xáo trộn thứ tự câu hỏi và các lựa chọn trong mỗi câu"""
    shuffled_parts = {}
    
    for part_key, part_data in QUESTIONS.items():
        shuffled_questions = part_data["questions"].copy()
        random.shuffle(shuffled_questions)
        
        for q in shuffled_questions:
            if "options" in q:
                original_options = q["options"].copy()
                shuffled_options = original_options.copy()
                random.shuffle(shuffled_options)
                q["shuffled_options"] = shuffled_options
                q["option_mapping"] = {opt: original_options.index(opt) for opt in shuffled_options}
            if "type" in q and q["type"] == "ordering":
                original_sentences = q["sentences"].copy()
                shuffled_sentences = original_sentences.copy()
                random.shuffle(shuffled_sentences)
                q["shuffled_sentences"] = shuffled_sentences
                q["correct_order_indices"] = [original_sentences.index(s) for s in q["correct_order"]]
        
        shuffled_parts[part_key] = {
            "title": part_data["title"],
            "image": part_data["image"],
            "questions": shuffled_questions
        }
    
    return shuffled_parts

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/get-questions")
async def get_questions():
    """Trả về câu hỏi đã được xáo trộn"""
    shuffled = shuffle_questions_and_options()
    return JSONResponse(content=shuffled)

@app.post("/submit")
async def handle_submit(request: Request):
    try:
        data = await request.json()
        user_answers = data.get("answers", {})
        
        # Tính điểm
        total_questions = 0
        correct_count = 0
        
        for part_key, part_data in QUESTIONS.items():
            for q in part_data["questions"]:
                total_questions += 1
                q_id = str(q["id"])
                user_answer = user_answers.get(q_id)
                
                if q.get("type") == "ordering":
                    # Xử lý câu hỏi sắp xếp thứ tự
                    if user_answer and isinstance(user_answer, list):
                        if user_answer == q["correct_order"]:
                            correct_count += 1
                else:
                    # Câu hỏi trắc nghiệm thường
                    if user_answer and user_answer == q["correct"]:
                        correct_count += 1
        
        # Tính điểm thang 10 (mỗi câu 0.25đ)
        score = (correct_count / total_questions) * 10 if total_questions > 0 else 0
        score_rounded = round(score, 2)
        
        # Đọc dữ liệu cũ
        submissions = []
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try: 
                    submissions = json.load(f)
                except: 
                    submissions = []
        
        # Tạo bản ghi mới
        now_utc = datetime.utcnow()
        now_vn = now_utc + timedelta(hours=7)
        
        new_entry = {
            "name": data.get("name", "Ẩn danh"),
            "score": f"{score_rounded}/10",
            "correct_count": f"{correct_count}/{total_questions}",
            "time": now_vn.strftime("%H:%M:%S %d/%m/%Y")
        }
        submissions.append(new_entry)
        
        # Ghi file
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(submissions, f, ensure_ascii=False, indent=4)
        
        return {
            "score": f"{score_rounded}/10",
            "correct_count": f"{correct_count}/{total_questions}",
            "time": new_entry["time"]
        }
        
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
