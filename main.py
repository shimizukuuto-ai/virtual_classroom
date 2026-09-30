import os
import random
import string
import shutil

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from db import init_pool, close_pool

from db import (
    init_db, create_user, get_user_by_name, get_user_by_id, set_user_lang,
    update_user_profile, set_user_skin, user_stats, calc_streak,
    list_classes_taught_by, list_weekly_classes,
    create_class, get_class_by_code, get_class_by_id, join_class,
    list_classes_for_user, list_public_classes, list_members, get_role,
    add_message, get_messages, get_message, mark_helpful, set_blackboard, set_stage,
    create_join_request, list_pending_requests_for_teacher, get_request_by_id,
    set_request_status, count_pending_for_teacher, list_my_requests,
    count_students, list_all_users, delete_user,
    save_blackboard_history, list_blackboard_history, get_blackboard_history_by_id,
    add_step, list_steps, delete_step,
    ban_user, unban_user, is_banned, list_bans, kick_user,
    create_question, list_questions, get_question, answer_question, delete_question,
    list_questions_answered_by,
    create_card, list_user_cards,
    list_user_badges, count_badges, check_badges, record_attendance, list_subjects,
    BADGES, SKINS, RANKS,
)
from i18n import all_t, default_steps


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "dev-only-key"))
templates = Jinja2Templates(directory="templates")

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


def gen_code():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def current_user(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        return None
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None
    return get_user_by_id(uid)


def ctx(request, user, **extra):
    lang = "ja"
    if user is not None:
        try:
            lang = (user["lang"] or "ja")
        except (KeyError, TypeError, IndexError):
            lang = "ja"
    base = {
        "request": request,
        "user": user,
        "T": all_t(lang),
        "lang": lang,
        # テンプレート側で参照されても落ちないようにデフォルトを入れる
        "flash": None,
        "pending_count": 0,
        "pending": [],
        "classes": [],
        "my_requests": [],
        "results": [],
        "q": "",
        "my_classes": set(),
        "error": None,
        "steps": [],
        "members": [],
        "messages": [],
        "questions": [],
        "bans": [],
        "profile_user": None,
        "stats": None,
        "taught": [],
        "recent_answers": [],
        "is_me": False,
        "default_steps": [],
        "cls": None,
        "role": None,
        "weekly": [],
        "earned_badges_count": 0,
        "earned_keys": set(),
        "earned": [],
        "streak": 0,
        "BADGES": BADGES,
        "SKINS": SKINS,
        "RANKS": RANKS,
        "cards": [],
    }
    base.update(extra)
    return base


@app.on_event("startup")
def startup():
    init_pool()


@app.on_event("shutdown")
def shutdown():
    close_pool()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse("/dashboard" if current_user(request) else "/login")


# ---- auth ----
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", ctx(request, None))


@app.post("/login")
def login_submit(request: Request, name: str = Form(...)):
    name = name.strip()
    if not name:
        return RedirectResponse("/login", status_code=303)
    user = get_user_by_name(name)
    if not user:
        create_user(name)
        user = get_user_by_name(name)
    request.session["user_id"] = int(user["id"])
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse({"ok": True, "id": int(user["id"]), "name": user["name"]})
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/lang/{code}")
def switch_lang(request: Request, code: str):
    user = current_user(request)
    if user and code in ("ja", "en"):
        set_user_lang(user["id"], code)
    return RedirectResponse(request.headers.get("referer") or "/dashboard")


# ---- profile ----
@app.get("/u/{uid}", response_class=HTMLResponse)
def profile_page(request: Request, uid: int):
    me = current_user(request)
    if not me:
        return RedirectResponse("/login")
    u = get_user_by_id(uid)
    if not u:
        return HTMLResponse("User not found", status_code=404)
    stats = user_stats(uid)
    taught = list_classes_taught_by(uid)
    recent_answers = list_questions_answered_by(uid, limit=10)
    is_me = (int(me["id"]) == int(uid))
    return templates.TemplateResponse(
        request, "profile.html",
        ctx(request, me, profile_user=u, stats=stats,
            taught=taught, recent_answers=recent_answers, is_me=is_me),
    )


@app.post("/u/{uid}/edit")
def profile_edit(request: Request, uid: int, title: str = Form(""), bio: str = Form("")):
    me = current_user(request)
    if not me or int(me["id"]) != int(uid):
        return RedirectResponse("/login")
    update_user_profile(uid, title.strip(), bio.strip())
    return RedirectResponse(f"/u/{uid}", status_code=303)


# ---- dashboard ----
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    classes = list_classes_for_user(user["id"])
    pending = list_pending_requests_for_teacher(user["id"])
    my_requests = list_my_requests(user["id"])
    pending_count = count_pending_for_teacher(user["id"])
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        request, "dashboard.html",
        ctx(request, user,
            classes=classes,
            pending=pending,
            my_requests=my_requests,
            pending_count=pending_count,
            flash=flash,
            stats=user_stats(user["id"]),
            streak=calc_streak(user["id"]),
            weekly=list_weekly_classes(limit=6),
            earned_badges_count=count_badges(user["id"])),
    )


# ---- browse ----
@app.get("/classes", response_class=HTMLResponse)
def browse_classes(request: Request, q: str = "", subject: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    raw = list_public_classes(q, subject)
    results = []
    for c in raw:
        d = dict(c)
        d["student_count"] = count_students(c["id"])
        results.append(d)
    my_classes = {c["id"] for c in list_classes_for_user(user["id"])}
    return templates.TemplateResponse(
        request, "browse.html",
        ctx(request, user, results=results, q=q, subject=subject,
            my_classes=my_classes, subjects=list_subjects()),
    )


@app.post("/classes/{class_id}/request")
def request_join(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    if is_banned(class_id, user["id"]):
        request.session["flash"] = "Banned"
        return RedirectResponse("/classes", status_code=303)
    if get_role(class_id, user["id"]):
        return RedirectResponse("/classes", status_code=303)
    create_join_request(class_id, user["id"])
    request.session["flash"] = "Join request sent"
    return RedirectResponse("/classes", status_code=303)


@app.post("/requests/{rid}/{action}")
def handle_request(request: Request, rid: int, action: str):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    req = get_request_by_id(rid)
    if not req:
        request.session["flash"] = "Request not found"
        return RedirectResponse("/dashboard", status_code=303)
    cls = get_class_by_id(req["class_id"])
    if not cls or cls["teacher_id"] != user["id"]:
        request.session["flash"] = "Not authorized"
        return RedirectResponse("/dashboard", status_code=303)
    if action == "approve":
        set_request_status(rid, "approved")
        join_class(req["class_id"], req["user_id"], role="student")
        request.session["flash"] = f"Approved user #{req['user_id']}"
    elif action == "reject":
        set_request_status(rid, "rejected")
        request.session["flash"] = f"Rejected user #{req['user_id']}"
    return RedirectResponse("/dashboard", status_code=303)


# ---- create / join ----
@app.get("/create_class", response_class=HTMLResponse)
def create_class_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    lang = (user["lang"] or "ja")
    return templates.TemplateResponse(
        request, "create_class.html",
        ctx(request, user, default_steps=default_steps(lang)),
    )


@app.post("/create_class")
def create_class_submit(
    request: Request,
    title: str = Form(...),
    subject: str = Form(...),
    description: str = Form(""),
    is_public: str = Form("1"),
    steps_text: str = Form(""),
    is_weekly: str = Form("0"),
    weekly_time: str = Form(""),
    next_session: str = Form(""),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    title, subject = title.strip(), subject.strip()
    if not title or not subject:
        return RedirectResponse("/create_class", status_code=303)
    cid = None
    for _ in range(5):
        cid = create_class(
            title, subject, description, user["id"], gen_code(),
            is_public=1 if is_public == "1" else 0,
            taught_by=user["name"],
            is_weekly=1 if is_weekly == "1" else 0,
            weekly_time=weekly_time.strip(),
            next_session=next_session.strip(),
        )
        if cid:
            break
    if not cid:
        return HTMLResponse("Failed to create class", status_code=500)
    for line in steps_text.splitlines():
        line = line.strip()
        if line:
            add_step(cid, line)
    return RedirectResponse(f"/class/{cid}", status_code=303)


@app.get("/join_class", response_class=HTMLResponse)
def join_class_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(
        request, "join_class.html", ctx(request, user, error=None)
    )


@app.post("/join_class")
def join_class_submit(request: Request, join_code: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    cls = get_class_by_code(join_code.strip().lower())
    if not cls:
        return templates.TemplateResponse(
            request, "join_class.html",
            ctx(request, user, error="No class with that code"),
            status_code=400,
        )
    if is_banned(cls["id"], user["id"]):
        return templates.TemplateResponse(
            request, "join_class.html",
            ctx(request, user, error="You are banned from this class"),
            status_code=403,
        )
    join_class(cls["id"], user["id"], role="student")
    return RedirectResponse(f"/class/{cls['id']}", status_code=303)


# ---- class room ----
@app.get("/class/{class_id}", response_class=HTMLResponse)
def class_room(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    cls = get_class_by_id(class_id)
    if not cls:
        return HTMLResponse("Class not found", status_code=404)
    if is_banned(class_id, user["id"]):
        return HTMLResponse("You are banned from this class.", status_code=403)
    role = get_role(class_id, user["id"])
    if not role:
        return HTMLResponse("Not a member", status_code=403)
    record_attendance(user["id"], class_id)
    check_badges(user["id"])
    members = list_members(class_id)
    messages = get_messages(class_id, limit=80)
    steps = list_steps(class_id)
    questions = list_questions(class_id, limit=100)
    bans = list_bans(class_id) if role == "teacher" else []
    return templates.TemplateResponse(
        request, "class_room.html",
        ctx(request, user, cls=cls, role=role, members=members,
            messages=messages, steps=steps, questions=questions, bans=bans),
    )


# ---- poll ----
@app.post("/api/poll/{class_id}")
async def api_poll(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if is_banned(class_id, user["id"]):
        return JSONResponse({"error": "banned"}, status_code=403)
    cls = get_class_by_id(class_id)
    if not cls:
        return JSONResponse({"error": "not found"}, status_code=404)
    msg = get_messages(class_id, limit=80)
    steps = list_steps(class_id)
    questions = list_questions(class_id, limit=100)
    members = list_members(class_id)
    return JSONResponse({
        "blackboard": cls["blackboard"] or "",
        "stage": cls["stage"] if "stage" in cls.keys() else 0,
        "steps": [{"id": s["id"], "title": s["title"]} for s in steps],
        "members": [{"id": m["user_id"], "name": m["name"], "role": m["role"], "skin": m["skin"] or "default"} for m in members],
        "messages": [
            {"id": m["id"], "type": m["sender_type"], "name": m["sender_name"],
             "content": m["content"], "helpful": m["helpful_count"] or 0}
            for m in msg
        ],
        "questions": [
            {"id": q["id"], "content": q["content"], "answer": q["answer"],
             "is_anonymous": q["is_anonymous"],
             "asker": q["asker_name"], "answerer": q["answerer_name"],
             "answered_at": q["answered_at"], "created_at": q["created_at"]}
            for q in questions
        ],
    })


# ---- blackboard ----
@app.post("/api/blackboard/{class_id}")
async def api_blackboard(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    data = await request.json()
    text = data.get("text", "")
    set_blackboard(class_id, text)
    save_blackboard_history(class_id, text, user["name"])
    return JSONResponse({"ok": True})


@app.post("/api/blackboard/clear/{class_id}")
async def api_blackboard_clear(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    set_blackboard(class_id, "")
    save_blackboard_history(class_id, "", user["name"])
    return JSONResponse({"ok": True})


# ---- upload ----
@app.post("/api/upload/{class_id}")
async def api_upload(request: Request, class_id: int, file: UploadFile = File(...)):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
    if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
        return JSONResponse({"error": "unsupported file type"}, status_code=400)
    safe_name = f"c{class_id}_{random.randint(10000, 99999)}.{ext}"
    path = os.path.join("static", "uploads", safe_name)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    url = f"/static/uploads/{safe_name}"
    return JSONResponse({"ok": True, "url": url})


# ---- steps ----
@app.post("/api/step/{class_id}/{action}")
async def api_step(request: Request, class_id: int, action: str):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    cls = get_class_by_id(class_id)
    steps = list_steps(class_id)
    total = len(steps)
    cur = cls["stage"] or 0
    if total == 0:
        cur = 0
    elif action == "next":
        cur = min(cur + 1, total - 1)
    elif action == "prev":
        cur = max(cur - 1, 0)
    set_stage(class_id, cur)
    return JSONResponse({"ok": True, "stage": cur, "total": total})


@app.post("/api/steps/{class_id}")
async def api_steps_add(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    data = await request.json()
    title = (data.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "empty"}, status_code=400)
    add_step(class_id, title, data.get("description", ""))
    return JSONResponse({"ok": True})


@app.post("/api/steps/{class_id}/{step_id}/delete")
async def api_steps_delete(request: Request, class_id: int, step_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    delete_step(step_id)
    return JSONResponse({"ok": True})


# ---- announce ----
@app.post("/api/announce/{class_id}")
async def api_announce(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if is_banned(class_id, user["id"]):
        return JSONResponse({"error": "banned"}, status_code=403)
    role = get_role(class_id, user["id"])
    if not role:
        return JSONResponse({"error": "not member"}, status_code=403)
    data = await request.json()
    text = (data.get("message") or "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)
    add_message(class_id, "user", user["name"], text)
    return JSONResponse({"ok": True})


# ---- helpful ----
@app.post("/api/helpful/{class_id}/{message_id}")
async def api_helpful(request: Request, class_id: int, message_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    m = get_message(message_id)
    if not m or m["class_id"] != class_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    if m["sender_name"] == user["name"]:
        return JSONResponse({"error": "cannot mark your own"}, status_code=400)
    ok, count = mark_helpful(message_id, user["id"])
    return JSONResponse({"ok": True, "count": count, "new": ok})


# ---- kick / ban ----
@app.post("/api/kick/{class_id}/{user_id}")
async def api_kick(request: Request, class_id: int, user_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    if int(user_id) == int(user["id"]):
        return JSONResponse({"error": "cannot kick yourself"}, status_code=400)
    kick_user(class_id, user_id)
    return JSONResponse({"ok": True})


@app.post("/api/ban/{class_id}/{user_id}")
async def api_ban(request: Request, class_id: int, user_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    if int(user_id) == int(user["id"]):
        return JSONResponse({"error": "cannot ban yourself"}, status_code=400)
    reason = ""
    try:
        data = await request.json()
        reason = (data.get("reason") or "").strip()
    except Exception:
        pass
    ban_user(class_id, user_id, reason)
    return JSONResponse({"ok": True})


@app.post("/api/unban/{class_id}/{user_id}")
async def api_unban(request: Request, class_id: int, user_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    unban_user(class_id, user_id)
    return JSONResponse({"ok": True})


# ---- questions (Q&A) ----
@app.post("/api/questions/{class_id}")
async def api_question_create(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if is_banned(class_id, user["id"]):
        return JSONResponse({"error": "banned"}, status_code=403)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    data = await request.json()
    content = (data.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "empty"}, status_code=400)
    is_anon = bool(data.get("anonymous", True))
    create_question(class_id, content, is_anon, user["id"])
    return JSONResponse({"ok": True})


@app.post("/api/questions/{class_id}/{qid}/answer")
async def api_question_answer(request: Request, class_id: int, qid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    q = get_question(qid)
    if not q or q["class_id"] != class_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    data = await request.json()
    answer = (data.get("answer") or "").strip()
    if not answer:
        return JSONResponse({"error": "empty"}, status_code=400)
    answer_question(qid, answer, user["id"])
    return JSONResponse({"ok": True})


@app.post("/api/questions/{class_id}/{qid}/delete")
async def api_question_delete(request: Request, class_id: int, qid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    q = get_question(qid)
    if not q or q["class_id"] != class_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    delete_question(qid)
    return JSONResponse({"ok": True})


# ---- history ----
@app.get("/api/history/{class_id}")
async def api_history(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    rows = list_blackboard_history(class_id, limit=50)
    return JSONResponse({
        "items": [
            {"id": r["id"], "content": r["content"] or "",
             "author": r["author"] or "", "created_at": r["created_at"]}
            for r in rows
        ]
    })


@app.post("/api/history/restore/{class_id}/{hid}")
async def api_history_restore(request: Request, class_id: int, hid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    r = get_blackboard_history_by_id(hid)
    if not r or r["class_id"] != class_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    set_blackboard(class_id, r["content"] or "")
    save_blackboard_history(class_id, r["content"] or "", f"{user['name']} (restore)")
    return JSONResponse({"ok": True, "content": r["content"] or ""})


# ---- badges / skins ----
@app.get("/badges", response_class=HTMLResponse)
def badges_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    earned = list_user_badges(user["id"])
    earned_keys = {b["badge_key"] for b in earned}
    stats = user_stats(user["id"])
    streak = calc_streak(user["id"])
    return templates.TemplateResponse(
        request, "badges.html",
        ctx(request, user, earned_keys=earned_keys, earned=earned,
            stats=stats, streak=streak),
    )


@app.post("/skin/{skin_key}")
def apply_skin(request: Request, skin_key: str):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    set_user_skin(user["id"], skin_key)
    return RedirectResponse(request.headers.get("referer") or "/badges", status_code=303)


@app.get("/api/stats/{uid}")
def api_stats(request: Request, uid: int):
    s = user_stats(uid)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    streak = calc_streak(uid)
    return JSONResponse({
        "xp": s["xp"],
        "rank": s["rank"][0],
        "rank_name": s["rank"][2],
        "badges": count_badges(uid),
        "streak": streak,
    })


# ---- learning card ----
@app.post("/card/{class_id}")
async def make_card(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    data = await request.json()
    content = (data.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "empty"}, status_code=400)
    create_card(user["id"], class_id, content)
    return JSONResponse({"ok": True})


@app.get("/cards", response_class=HTMLResponse)
def cards_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    cards = list_user_cards(user["id"], limit=50)
    return templates.TemplateResponse(
        request, "cards.html", ctx(request, user, cards=cards)
    )

# ---- invite (magic link) ----
@app.get("/invite/{join_code}", response_class=HTMLResponse)
def invite_page(request: Request, join_code: str):
    cls = get_class_by_code(join_code.strip().lower())
    if not cls:
        return templates.TemplateResponse(
            request, "invite.html",
            ctx(request, current_user(request), invite_cls=None, join_code=join_code),
            status_code=404,
        )
    me = current_user(request)
    return templates.TemplateResponse(
        request, "invite.html",
        ctx(request, me, invite_cls=cls, join_code=join_code.strip().lower()),
    )


@app.post("/invite/{join_code}")
def invite_join(request: Request, join_code: str, name: str = Form(...)):
    cls = get_class_by_code(join_code.strip().lower())
    if not cls:
        return RedirectResponse(f"/invite/{join_code}", status_code=303)
    name = name.strip()
    if not name:
        return RedirectResponse(f"/invite/{join_code}", status_code=303)
    user = get_user_by_name(name)
    if not user:
        create_user(name)
        user = get_user_by_name(name)
    request.session["user_id"] = int(user["id"])
    if is_banned(cls["id"], user["id"]):
        return HTMLResponse("You are banned from this class.", status_code=403)
    join_class(cls["id"], user["id"], role="student")
    return RedirectResponse(f"/class/{cls['id']}", status_code=303)


# ---- dev (ENABLE_DEV=1 のみ) ----
if os.environ.get("ENABLE_DEV") == "1":
    @app.get("/dev/users", response_class=HTMLResponse)
    def dev_users(request: Request):
        users = list_all_users()
        return templates.TemplateResponse(
            request, "dev_users.html", ctx(request, None, users=users)
        )

    @app.post("/dev/users/create")
    def dev_create_user(request: Request, name: str = Form(...), count: int = Form(1)):
        name = name.strip()
        if not name:
            return RedirectResponse("/dev/users", status_code=303)
        for i in range(max(1, min(count, 50))):
            suffix = f"{i+1:02d}" if count > 1 else ""
            try:
                create_user(f"{name}{suffix}")
            except Exception:
                pass
        return RedirectResponse("/dev/users", status_code=303)

    @app.get("/dev/login_as/{uid}", response_class=HTMLResponse)
    def dev_login_as(request: Request, uid: int):
        u = get_user_by_id(uid)
        if not u:
            return RedirectResponse("/dev/users", status_code=303)
        request.session["user_id"] = int(u["id"])
        return RedirectResponse("/dashboard", status_code=303)

    @app.post("/dev/delete/{uid}")
    def dev_delete(request: Request, uid: int):
        delete_user(uid)
        return RedirectResponse("/dev/users", status_code=303)