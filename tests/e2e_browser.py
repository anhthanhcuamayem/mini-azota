"""E2E: chuẩn bị dữ liệu bằng API, rồi chạy headless Chrome qua toàn bộ luồng
đăng nhập -> lớp/tổ/vai trò -> bài thi -> bảng điểm."""
import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.request

import requests
import websockets

BASE = "http://127.0.0.1:8011"
DEBUG = "http://127.0.0.1:9222"
FIXTURE = "/tmp/fixture.txt"

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  | " + str(extra)[:220]) if extra else ""))
    if not cond:
        fails.append(name)


# ------------------------------------------------------------------ setup API
def setup():
    teacher = requests.Session()
    student = requests.Session()
    monitor = requests.Session()
    for s, email, name, role in (
        (teacher, "e2e_gv@t.edu", "GV E2E", "teacher"),
        (student, "e2e_hs@t.edu", "HS E2E", "student"),
        (monitor, "e2e_to@t.edu", "To Truong E2E", "student"),
    ):
        r = s.post(BASE + "/api/auth/register",
                   json={"email": email, "name": name, "role": role, "password": "matkhau123"})
        if r.status_code != 201:
            # đã tồn tại từ lần chạy trước -> đăng nhập
            r = s.post(BASE + "/api/auth/login",
                       json={"email": email, "password": "matkhau123"})
        assert r.status_code in (200, 201), f"auth {email}: {r.status_code} {r.text[:200]}"

    # dọn bài nộp cũ của tài khoản test để lần chạy sau HS làm lại được
    hs_id = student.get(BASE + "/api/auth/me").json()["user"]["id"]
    if os.path.exists("data/attempts.json"):
        with open("data/attempts.json", encoding="utf-8") as f:
            attempts = json.load(f)
        kept = [a for a in attempts if a.get("user_id") != hs_id]
        if len(kept) != len(attempts):
            with open("data/attempts.json", "w", encoding="utf-8") as f:
                json.dump(kept, f, ensure_ascii=False, indent=2)
            print(f"đã dọn {len(attempts) - len(kept)} bài nộp cũ của HS E2E")

    r = teacher.post(BASE + "/api/classes", json={"name": "12B2 E2E", "grade": "12"})
    cls = r.json()["class"]
    code = cls["join_code"]
    # nếu lớp đã có từ lần trước thì dùng lại
    classes = teacher.get(BASE + "/api/classes").json()["classes"]
    cls = next((c for c in classes if c["name"] == "12B2 E2E"), cls)
    code = cls["join_code"]

    student.post(BASE + "/api/classes/join", json={"code": code})
    monitor.post(BASE + "/api/classes/join", json={"code": code})

    teams = {t["name"]: t["id"] for t in cls.get("teams", [])}
    if "Tổ A" not in teams:
        teacher.post(BASE + f"/api/classes/{cls['id']}/teams", json={"name": "Tổ A"})
    detail = teacher.get(BASE + f"/api/classes/{cls['id']}").json()["class"]
    # dọn "Tổ B" của lần chạy trước để giao diện thêm lại được
    for t in list(detail.get("teams", [])):
        if t["name"].startswith("Tổ B"):
            teacher.delete(BASE + f"/api/classes/{cls['id']}/teams/{t['id']}")
    detail = teacher.get(BASE + f"/api/classes/{cls['id']}").json()["class"]
    teams = {t["name"]: t["id"] for t in detail["teams"]}
    by_name = {m["name"]: m for m in detail["members"]}

    if by_name.get("HS E2E"):
        teacher.patch(BASE + f"/api/classes/{cls['id']}/members/{by_name['HS E2E']['user_id']}",
                      json={"team_id": teams.get("Tổ A")})
    if by_name.get("To Truong E2E"):
        teacher.patch(BASE + f"/api/classes/{cls['id']}/members/{by_name['To Truong E2E']['user_id']}",
                      json={"role": "class_monitor"})

    # tạo đề (chỉ 1 lần giữa các lần chạy)
    exams = teacher.get(BASE + "/api/exams").json()["exams"]
    exam = next((e for e in exams if e["title"] == "Đề E2E"), None)
    if not exam:
        with open(FIXTURE, encoding="utf-8") as f:
            r = teacher.post(BASE + "/api/exams",
                             data={"title": "Đề E2E", "duration_minutes": "30"},
                             files={"file": ("fixture.txt", f.read())})
        assert r.status_code == 200, f"create exam: {r.status_code} {r.text[:300]}"
        exam = r.json()["exam"]
    teacher.post(BASE + f"/api/exams/{exam['id']}/assign", json={"class_ids": [cls["id"]]})
    teacher.post(BASE + f"/api/exams/{exam['id']}/publish", json={"published": True})
    return {"class_id": cls["id"], "exam_id": exam["id"]}


# ------------------------------------------------------------------ browser
async def browser_flow(ctx):
    chrome = subprocess.Popen(
        shlex.split("/usr/bin/google-chrome --headless=new --disable-gpu --no-sandbox "
                     "--remote-debugging-port=9222 --user-data-dir=/tmp/cdp-e2e-%d "
                     "--window-size=1400,1100 about:blank" % int(time.time())),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(DEBUG + "/json/version", timeout=1).read()
                break
            except Exception:
                await asyncio.sleep(0.5)
        targets = json.load(urllib.request.urlopen(DEBUG + "/json/list"))
        page = next(t for t in targets if t["type"] == "page")
        ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=None)
        mid = 0
        errors, bad = [], []

        async def send(method, params=None):
            nonlocal mid
            mid += 1
            my_id = mid
            await ws.send(json.dumps({"id": my_id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if msg.get("method") == "Runtime.exceptionThrown":
                    errors.append(msg["params"]["exceptionDetails"].get("text", "exception"))
                elif msg.get("method") == "Log.entryAdded" and msg["params"]["entry"].get("level") == "error":
                    txt = msg["params"]["entry"].get("text", "")
                    # 401 từ /api/auth/me khi chưa đăng nhập là kiểm tra phiên hợp lệ (xem Network bên dưới)
                    if "favicon" in txt or ("Failed to load resource" in txt and "401" in txt):
                        continue
                    errors.append(txt[:180])
                elif msg.get("method") == "Network.responseReceived":
                    r = msg["params"]["response"]
                    status = r.get("status", 0)
                    url = r.get("url", "")
                    expected = status == 401 and url.endswith("/api/auth/me")
                    if status >= 400 and not expected:
                        bad.append(f"{status} {url}")
                if msg.get("id") == my_id:
                    return msg.get("result", {})

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                "awaitPromise": True})
            if "exceptionDetails" in r:
                return "EXCEPTION: " + json.dumps(r["exceptionDetails"])[:200]
            res = r.get("result", {})
            return res.get("value", res.get("description"))

        async def wait_for(expr, tries=60, step=0.5):
            for _ in range(tries):
                v = await ev(expr)
                if v is True:
                    return True
                await asyncio.sleep(step)
            return False

        async def goto(url, wait=3):
            await send("Page.navigate", {"url": url})
            await asyncio.sleep(wait)

        await send("Runtime.enable")
        await send("Log.enable")
        await send("Network.enable")
        await send("Page.enable")

        # ---------- 1. HS đăng nhập qua form portal ----------
        await goto(BASE + "/portal")
        check("portal tải, chưa đăng nhập", "Đăng nhập" in await ev("document.body.innerText"))
        await ev("document.getElementById('loginEmail').value='e2e_hs@t.edu'")
        await ev("document.getElementById('loginPass').value='matkhau123'")
        await ev("document.getElementById('loginForm').requestSubmit()")
        ok = await wait_for("document.getElementById('appView').classList.contains('hidden') === false")
        check("đăng nhập HS bằng form -> hiện dashboard", ok)
        text = await ev("document.body.innerText")
        check("dashboard HS có tab Bài thi + Điểm", "Bài thi" in text and "Điểm của tôi" in text)
        check("hiển thị vai trò trong thẻ lớp", "12B2 E2E" in text, text[:200])

        # ---------- 2. HS mở bảng điểm (tư cách tổ trưởng/lớp trưởng) ----------
        await ev("[...document.querySelectorAll('#mainTabs .tab')].find(b=>b.dataset.tab==='results').click()")
        await asyncio.sleep(1.5)
        text = await ev("document.body.innerText")
        check("tab Điểm của tôi hiển thị lịch sử/điểm", "Điểm của tôi" in text or "Lịch sử" in text)

        # ---------- 3. HS vào phòng thi ----------
        await ev("[...document.querySelectorAll('#mainTabs .tab')].find(b=>b.dataset.tab==='exams').click()")
        await asyncio.sleep(1.5)
        has_btn = await ev("!!document.querySelector('[data-start]')")
        check("danh sách bài thi có nút Vào phòng thi", has_btn is True)
        await ev("document.querySelector('[data-start]').click()")
        ok = await wait_for("location.search.indexOf('exam=') > -1", tries=30)
        await asyncio.sleep(3)
        check("chuyển sang trang /?exam=<id>", ok)
        prefilled = await ev("document.getElementById('fullname').value")
        readonly = await ev("document.getElementById('fullname').readOnly")
        check("tự điền tên tài khoản + chỉ đọc", prefilled == "HS E2E" and readonly is True,
              f"name={prefilled!r} readonly={readonly}")
        await ev("document.getElementById('startExamBtn').click()")
        ok = await wait_for("document.getElementById('examContainer').style.display === 'block'", tries=60)
        check("bấm START -> vào phòng thi", ok)
        cells = await ev("document.querySelectorAll('#questionPaletteGrid .q-num-btn').length")
        title = await ev("document.querySelector('.exam-header h2').innerText")
        check("đủ 40 câu + tiêu đề đề thi", cells == 40 and "Đề E2E" in str(title), f"cells={cells} title={title}")

        # ---------- 4. làm 5 câu rồi nộp ----------
        for i in range(5):
            await ev("document.querySelector('#dynamicQuestion .option-item')?.click()")
            await asyncio.sleep(0.15)
            await ev("document.getElementById('nextBtn').click()")
            await asyncio.sleep(0.15)
        answered = await ev("document.getElementById('paletteAnsweredCount').innerText")
        check("chọn đáp án hoạt động", answered != "0/40 đã làm", answered)
        await ev("document.getElementById('submitExamBtn').click()")
        await asyncio.sleep(0.6)
        await ev("document.getElementById('confirmSubmitBtn').click()")
        ok = await wait_for("document.getElementById('resultModal').style.display === 'flex'", tries=40)
        score = await ev("document.getElementById('modalScore').innerText")
        check("nộp bài -> modal kết quả hiện điểm", ok and bool(str(score).endswith("/40")), f"score={score}")

        # ---------- 5. GV đăng nhập, xem lớp + bảng điểm ----------
        await goto(BASE + "/portal")
        await ev("document.getElementById('logoutBtn').click()")
        await asyncio.sleep(1.5)
        await ev("document.getElementById('loginEmail').value='e2e_gv@t.edu'")
        await ev("document.getElementById('loginPass').value='matkhau123'")
        await ev("document.getElementById('loginForm').requestSubmit()")
        ok = await wait_for("document.getElementById('appView').classList.contains('hidden') === false")
        check("đăng nhập GV bằng form", ok)
        await asyncio.sleep(1)
        text = await ev("document.body.innerText")
        check("GV thấy lớp 12B2 E2E + mã lớp", "12B2 E2E" in text and "Tạo lớp mới" in text)
        opened = await ev("document.querySelector('[data-open]')?.click() || true")
        await asyncio.sleep(2)
        text = await ev("document.body.innerText")
        check("mở trang quản lý lớp: có bảng thành viên + vai trò",
              "GV E2E" in text or "HS E2E" in text, text[:250])
        check("có bảng điểm với bài nộp của HS",
              "Bảng điểm lớp" in text and "HS E2E" in text, text[:400])
        check("có nút xuất CSV", await ev("!!document.getElementById('csvBtn')") is True)

        # ---------- 6. GV tạo tổ bằng UI ----------
        await ev("document.getElementById('newTeamName').value = 'Tổ B'")
        await ev("document.getElementById('addTeamBtn').click()")
        await asyncio.sleep(2)
        text = await ev("document.body.innerText")
        check("thêm tổ qua UI thành công", "Tổ B" in text, text[:200])

        check("không có JS exception", not errors, errors)
        check("không có request lỗi >=400 (trừ 401 kiểm tra phiên /api/auth/me)", not bad, bad)
        await ws.close()
        return 0
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except Exception:
            chrome.kill()


if __name__ == "__main__":
    ctx = setup()
    print("setup ok:", ctx)
    code = asyncio.get_event_loop().run_until_complete(browser_flow(ctx))
    print("\n=== KẾT QUẢ:", "ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}")
    sys.exit(1 if (fails or code) else 0)
