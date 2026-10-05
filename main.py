import os
import random
import string
import shutil
import base64

from fastapi import FastAPI, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from db import (
    init_pool, close_pool,
    create_user, get_user_by_name, get_user_by_id, set_user_lang,
    update_user_profile, set_user_skin, user_stats, calc_streak,
    list_classes_taught_by, list_weekly_classes,
    create_class, get_class_by_code, get_class_by_id, join_class,
    list_classes_for_user, list_public_classes, list_subjects,
    list_members, get_role,
    add_message, get_messages, get_message, mark_helpful, mark_like,
    set_blackboard, set_stage, set_allow_anonymous,
    create_join_request, list_pending_requests_for_teacher, get_request_by_id,
    set_request_status, count_pending_for_teacher, list_my_requests,
    count_students, list_all_users, delete_user,
    save_blackboard_history, list_blackboard_history, get_blackboard_history_by_id,
    add_step, list_steps, delete_step,
    ban_user, unban_user, is_banned, list_bans, kick_user,
    create_question, list_questions, get_question, answer_question, delete_question,
    list_questions_answered_by,
    create_card, list_user_cards,
    list_user_badges, count_badges, check_badges, record_attendance,
    add_bonus_xp, reset_bonus_xp,
    add_class_file, list_class_files,
    create_group, list_groups, delete_group, add_member_to_group,
    remove_member_from_group, get_user_group, set_group_board,
    add_student_note, list_student_notes, delete_student_note,
    save_upload, get_upload,    set_user_customization, get_unlock_tier, UNLOCK_TIERS,
    rate_teacher, get_teacher_rating, get_my_rating,
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
    lang = "en"
    if user is not None:
        try:
            lang = (user["lang"] or "en")
        except (KeyError, TypeError, IndexError):
            lang = "en"
    base = {
        "request": request,
        "user": user,
        "T": all_t(lang),
        "lang": lang,
        "flash": None,
        "pending_count": 0,
        "pending": [],
        "classes": [],
        "my_requests": [],
        "results": [],
        "q": "",
        "subject": "",
        "subjects": [],
        "my_classes": set(),
        "error": None,
        "mode": "email",
        "email": "",
        "steps": [],
        "members": [],
        "messages": [],
        "questions": [],
        "bans": [],
        "files": [],
        "groups": [],
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
        "invite_cls": None,
        "join_code": "",
        "allow_anonymous": False,
        "notes": [],
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


# ============================================================
# auth
# ============================================================
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


# ============================================================
# profile
# ============================================================
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


# ============================================================
# dashboard
# ============================================================
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


# ============================================================
# browse
# ============================================================
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


@app.get("/classes/{class_id}/open")
def open_class(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    cls = get_class_by_id(class_id)
    if not cls:
        return RedirectResponse("/classes", status_code=303)
    if cls["is_public"] != 2:
        return RedirectResponse("/classes", status_code=303)
    if is_banned(class_id, user["id"]):
        return RedirectResponse("/classes", status_code=303)
    join_class(class_id, user["id"], role="student")
    return RedirectResponse(f"/class/{class_id}", status_code=303)


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


# ============================================================
# create / join
# ============================================================
@app.get("/create_class", response_class=HTMLResponse)
def create_class_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    lang = (user["lang"] or "en")
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
    allow_anonymous: str = Form("0"),
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
            is_public=int(is_public) if is_public in ("0", "1", "2") else 1,
            taught_by=user["name"],
            is_weekly=1 if is_weekly == "1" else 0,
            weekly_time=weekly_time.strip(),
            next_session=next_session.strip(),
            allow_anonymous=1 if allow_anonymous == "1" else 0,
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


# ============================================================
# class room
# ============================================================
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
    members = list_members(class_id)
    messages = get_messages(class_id, limit=80)
    steps = list_steps(class_id)
    questions = list_questions(class_id, limit=100)
    bans = list_bans(class_id) if role == "teacher" else []
    files = list_class_files(class_id, limit=30)
    groups = list_groups(class_id)
    my_group = get_user_group(class_id, user["id"]) if role == "student" else None
    return templates.TemplateResponse(
        request, "class_room.html",
        ctx(request, user, cls=cls, role=role, members=members,
            messages=messages, steps=steps, questions=questions, bans=bans,
            files=files, groups=groups, my_group=my_group,
            allow_anonymous=bool(cls.get("allow_anonymous") or 0)),
    )


# ============================================================
# poll
# ============================================================
@app.post("/api/poll/{class_id}")
async def api_poll(request: Request, class_id: int, since_id: int = 0):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if is_banned(class_id, user["id"]):
        return JSONResponse({"error": "banned"}, status_code=403)
    cls = get_class_by_id(class_id)
    if not cls:
        return JSONResponse({"error": "not found"}, status_code=404)
    role = get_role(class_id, user["id"])
    if not role:
        return JSONResponse({"error": "not member"}, status_code=403)
    msg = get_messages(class_id, limit=80)
    steps = list_steps(class_id)
    questions = list_questions(class_id, limit=100)
    members = list_members(class_id)
    files = list_class_files(class_id, limit=30)
    groups = list_groups(class_id)
    my_group = get_user_group(class_id, user["id"]) if role == "student" else None
    return JSONResponse({
        "blackboard": cls["blackboard"] or "",
        "stage": cls["stage"] or 0,
        "allow_anonymous": bool(cls.get("allow_anonymous") or 0),
        "steps": [{"id": s["id"], "title": s["title"]} for s in steps],
                "members": [{
            "id": m["user_id"], "name": m["name"], "role": m["role"],
            "skin": m["skin"] or "default",
            "custom_hair": m["custom_hair"] if m.get("custom_hair") is not None else -1,
            "custom_skin": m["custom_skin"] if m.get("custom_skin") is not None else -1,
            "custom_shirt": m["custom_shirt"] if m.get("custom_shirt") is not None else -1,
            "custom_style": m.get("custom_style") or "",
        } for m in members],
        "messages": [
            {"id": m["id"], "type": m["sender_type"], "name": m["sender_name"],
             "content": m["content"], "helpful": m["helpful_count"] or 0,
             "like": m["like_count"] or 0}
            for m in msg
        ],
        "questions": [
            {"id": q["id"], "content": q["content"], "answer": q["answer"],
             "is_anonymous": q["is_anonymous"],
             "asker": q["asker_name"], "answerer": q["answerer_name"],
             "answered_at": q["answered_at"], "created_at": q["created_at"]}
            for q in questions
        ],
        "files": [
            {"id": f["id"], "filename": f["filename"], "url": f["url"]}
            for f in files
        ],
        "groups": groups,
        "my_group": dict(my_group) if my_group else None,
    })


# ============================================================
# blackboard
# ============================================================
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


# ============================================================
# image serving (persistent, DB-backed)
# ============================================================
@app.get("/api/image/{upload_id}")
def serve_image(upload_id: int):
    row = get_upload(upload_id)
    if not row:
        return Response(status_code=404)
    raw = base64.b64decode(row["data"])
    return Response(content=raw, media_type=row["mime"])


# ============================================================
# upload (image / pdf / draw) — all DB-backed
# ============================================================
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
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        return JSONResponse({"error": "too large"}, status_code=400)
    mime = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp",
    }[ext]
    b64 = base64.b64encode(raw).decode("ascii")
    uid = save_upload(b64, mime, len(raw), kind="image")
    url = f"/api/image/{uid}"
    return JSONResponse({"ok": True, "url": url, "ext": ext})


@app.post("/api/upload_pdf/{class_id}")
async def api_upload_pdf(request: Request, class_id: int, file: UploadFile = File(...)):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
    if ext != "pdf":
        return JSONResponse({"error": "pdf only"}, status_code=400)
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        return JSONResponse({"error": "too large (max 10MB)"}, status_code=400)
    b64 = base64.b64encode(raw).decode("ascii")
    uid = save_upload(b64, "application/pdf", len(raw), kind="pdf")
    url = f"/api/image/{uid}"
    original = file.filename or "file.pdf"
    add_class_file(class_id, original, url, "application/pdf", user["id"])
    return JSONResponse({"ok": True, "url": url, "name": original})


@app.post("/api/upload_draw/{class_id}")
async def api_upload_draw(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    data = await request.json()
    data_url = data.get("data", "")
    if not data_url.startswith("data:image/png;base64,"):
        return JSONResponse({"error": "invalid data"}, status_code=400)
    b64 = data_url.split(",", 1)[1]
    raw = base64.b64decode(b64)
    if len(raw) > 3 * 1024 * 1024:
        return JSONResponse({"error": "too large"}, status_code=400)
    uid = save_upload(b64, "image/png", len(raw), kind="draw")
    url = f"/api/image/{uid}"
    return JSONResponse({"ok": True, "url": url})


# ============================================================
# steps
# ============================================================
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


# ============================================================
# announce
# ============================================================
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


# ============================================================
# helpful / like
# ============================================================
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


@app.post("/api/like/{class_id}/{message_id}")
async def api_like(request: Request, class_id: int, message_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    m = get_message(message_id)
    if not m or m["class_id"] != class_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    ok, count = mark_like(message_id, user["id"])
    return JSONResponse({"ok": True, "count": count, "new": ok})


# ============================================================
# kick / ban
# ============================================================
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


# ============================================================
# questions
# ============================================================
@app.post("/api/questions/{class_id}")
async def api_question_create(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if is_banned(class_id, user["id"]):
        return JSONResponse({"error": "banned"}, status_code=403)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    cls = get_class_by_id(class_id)
    data = await request.json()
    content = (data.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "empty"}, status_code=400)
    allow = bool(cls and cls.get("allow_anonymous"))
    is_anon = bool(data.get("anonymous", False)) and allow
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


@app.post("/api/class/{class_id}/allow_anonymous")
async def api_set_allow_anonymous(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    data = await request.json()
    allow = bool(data.get("allow", False))
    set_allow_anonymous(class_id, 1 if allow else 0)
    return JSONResponse({"ok": True, "allow": allow})


# ============================================================
# history
# ============================================================
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


# ============================================================
# groups
# ============================================================
@app.post("/api/groups/{class_id}")
async def api_group_create(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "empty"}, status_code=400)
    gid = create_group(class_id, name)
    return JSONResponse({"ok": True, "id": gid})


@app.post("/api/groups/{class_id}/{gid}/delete")
async def api_group_delete(request: Request, class_id: int, gid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    delete_group(gid)
    return JSONResponse({"ok": True})


@app.post("/api/groups/{class_id}/{gid}/members/{uid}")
async def api_group_add_member(request: Request, class_id: int, gid: int, uid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    remove_member_from_group(gid, uid)
    add_member_to_group(gid, uid)
    return JSONResponse({"ok": True})


@app.post("/api/groups/{class_id}/{gid}/members/{uid}/remove")
async def api_group_remove_member(request: Request, class_id: int, gid: int, uid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    remove_member_from_group(gid, uid)
    return JSONResponse({"ok": True})


@app.post("/api/groups/{class_id}/{gid}/board")
async def api_group_board(request: Request, class_id: int, gid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    role = get_role(class_id, user["id"])
    if not role:
        return JSONResponse({"error": "not member"}, status_code=403)
    if role != "teacher":
        grp = get_user_group(class_id, user["id"])
        if not grp or grp["id"] != gid:
            return JSONResponse({"error": "not your group"}, status_code=403)
    data = await request.json()
    content = data.get("content", "")
    set_group_board(gid, content)
    return JSONResponse({"ok": True})


# ============================================================
# student notes
# ============================================================
@app.post("/api/notes/{class_id}")
async def api_note_create(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    data = await request.json()
    content = (data.get("content") or "").strip()
    title = (data.get("title") or "").strip()
    if not content:
        return JSONResponse({"error": "empty"}, status_code=400)
    add_student_note(user["id"], class_id, content, title)
    return JSONResponse({"ok": True})


@app.get("/api/notes/{class_id}")
async def api_note_list(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if not get_role(class_id, user["id"]):
        return JSONResponse({"error": "not member"}, status_code=403)
    rows = list_student_notes(user["id"], class_id, limit=50)
    return JSONResponse({
        "items": [
            {"id": r["id"], "title": r["title"] or "", "content": r["content"], "created_at": r["created_at"]}
            for r in rows
        ]
    })


@app.post("/api/notes/{class_id}/{nid}/delete")
async def api_note_delete(request: Request, class_id: int, nid: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    delete_student_note(nid, user["id"])
    return JSONResponse({"ok": True})


# ============================================================
# badges / skins
# ============================================================
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
    return JSONResponse({
        "xp": s["xp"], "rank": s["rank"][0], "rank_name": s["rank"][2],
        "badges": count_badges(uid), "streak": calc_streak(uid),
    })


# ============================================================
# cards
# ============================================================
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


# ============================================================
# invite
# ============================================================
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


# ============================================================
# audio websocket
# ============================================================
audio_rooms: dict = {}


@app.websocket("/ws/audio/{class_id}")
async def audio_ws(websocket: WebSocket, class_id: int):
    session = websocket.session
    uid = session.get("user_id")
    if not uid:
        await websocket.close(code=1008)
        return
    user = get_user_by_id(int(uid))
    if not user:
        await websocket.close(code=1008)
        return
    cls = get_class_by_id(class_id)
    if not cls:
        await websocket.close(code=1008)
        return
    role = get_role(class_id, user["id"])
    if not role:
        await websocket.close(code=1008)
        return
    if is_banned(class_id, user["id"]):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    audio_rooms.setdefault(class_id, [])
    audio_rooms[class_id].append(websocket)

    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data and data["bytes"] is not None:
                if role != "teacher":
                    continue
                payload = data["bytes"]
                for ws in list(audio_rooms.get(class_id, [])):
                    if ws is websocket:
                        continue
                    try:
                        await ws.send_bytes(payload)
                    except Exception:
                        pass
            elif "text" in data and data["text"] == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if class_id in audio_rooms:
            try:
                audio_rooms[class_id].remove(websocket)
            except ValueError:
                pass
            if not audio_rooms[class_id]:
                del audio_rooms[class_id]

# ============================================================
# customization
# ============================================================
@app.get("/customize", response_class=HTMLResponse)
def customize_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    stats = user_stats(user["id"])
    tiers = {k: get_unlock_tier(user["id"], k) for k in UNLOCK_TIERS.keys()}
    return templates.TemplateResponse(
        request, "customize.html",
        ctx(request, user, stats=stats, tiers=tiers),
    )


@app.post("/customize")
def customize_submit(
    request: Request,
    hair: str = Form(...),
    skin: str = Form(...),
    shirt: str = Form(...),
    style: str = Form(""),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    try:
        set_user_customization(
            user["id"],
            hair=int(hair) if hair != "" else -1,
            skin=int(skin) if skin != "" else -1,
            shirt=int(shirt) if shirt != "" else -1,
            style=style or "",
        )
    except (ValueError, TypeError):
        pass
    return RedirectResponse("/customize", status_code=303)


# ============================================================
# teacher ratings
# ============================================================
@app.post("/api/rate/{class_id}/{teacher_id}")
async def api_rate(request: Request, class_id: int, teacher_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    role = get_role(class_id, user["id"])
    if not role:
        return JSONResponse({"error": "not member"}, status_code=403)
    if int(user["id"]) == int(teacher_id):
        return JSONResponse({"error": "cannot rate yourself"}, status_code=400)
    data = await request.json()
    value = int(data.get("value", 0))
    if value not in (1, -1):
        return JSONResponse({"error": "invalid value"}, status_code=400)
    rate_teacher(teacher_id, user["id"], class_id, value)
    return JSONResponse({"ok": True})


@app.get("/api/rating/{teacher_id}")
def api_rating(request: Request, teacher_id: int):
    r = get_teacher_rating(teacher_id)
    return JSONResponse({
        "good": r["good"] if r else 0,
        "bad": r["bad"] if r else 0,
        "total": r["total"] if r else 0,
    })

# ============================================================
# dev
# ============================================================
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

    @app.post("/dev/xp/add/{amount}")
    def dev_xp_add(request: Request, amount: int):
        user = current_user(request)
        if not user:
            return RedirectResponse("/login")
        add_bonus_xp(user["id"], amount)
        return RedirectResponse(request.headers.get("referer") or "/badges", status_code=303)

    @app.post("/dev/xp/reset")
    def dev_xp_reset(request: Request):
        user = current_user(request)
        if not user:
            return RedirectResponse("/login")
        reset_bonus_xp(user["id"])
        return RedirectResponse(request.headers.get("referer") or "/badges", status_code=303)