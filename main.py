import os
import shutil
import random
import string

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from db import (
    init_db, create_user, get_user_by_name, get_user_by_id, set_user_lang,
    create_class, get_class_by_code, get_class_by_id, join_class,
    list_classes_for_user, list_public_classes, list_members, get_role,
    add_message, get_messages, set_blackboard, set_stage,
    create_join_request, list_pending_requests_for_teacher, get_request_by_id,
    set_request_status, count_pending_for_teacher, list_my_requests,
    count_students, list_all_users, delete_user,
    save_blackboard_history, list_blackboard_history, get_blackboard_history_by_id,
)
from i18n import all_t, stages as stage_list


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "dev-only-key"))
templates = Jinja2Templates(directory="templates")

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


def gen_code():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def current_user(request: Request):
    h = request.headers.get("X-User-Id")
    if h:
        try:
            u = get_user_by_id(int(h))
            if u:
                return u
        except (ValueError, TypeError):
            pass
    q = request.query_params.get("uid")
    if q:
        try:
            u = get_user_by_id(int(q))
            if u:
                return u
        except (ValueError, TypeError):
            pass
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
        "STAGES": stage_list(lang),
    }
    base.update(extra)
    return base


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse("/dashboard" if current_user(request) else "/login")


# ---------- auth ----------
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


# ---------- dashboard ----------
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
            classes=classes, pending=pending,
            my_requests=my_requests, pending_count=pending_count,
            flash=flash),
    )


# ---------- browse ----------
@app.get("/classes", response_class=HTMLResponse)
def browse_classes(request: Request, q: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    raw = list_public_classes(q)
    results = []
    for c in raw:
        d = dict(c)
        d["student_count"] = count_students(c["id"])
        results.append(d)
    my_classes = {c["id"] for c in list_classes_for_user(user["id"])}
    return templates.TemplateResponse(
        request, "browse.html",
        ctx(request, user, results=results, q=q, my_classes=my_classes),
    )


@app.post("/classes/{class_id}/request")
def request_join(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
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


# ---------- create / join ----------
@app.get("/create_class", response_class=HTMLResponse)
def create_class_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(request, "create_class.html", ctx(request, user))


@app.post("/create_class")
def create_class_submit(
    request: Request,
    title: str = Form(...),
    subject: str = Form(...),
    description: str = Form(""),
    is_public: str = Form("1"),
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
        )
        if cid:
            break
    if not cid:
        return HTMLResponse("Failed to create class", status_code=500)
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
    join_class(cls["id"], user["id"], role="student")
    return RedirectResponse(f"/class/{cls['id']}", status_code=303)


# ---------- class room ----------
@app.get("/class/{class_id}", response_class=HTMLResponse)
def class_room(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    cls = get_class_by_id(class_id)
    if not cls:
        return HTMLResponse("Class not found", status_code=404)
    role = get_role(class_id, user["id"])
    if not role:
        return HTMLResponse("Not a member", status_code=403)
    members = list_members(class_id)
    messages = get_messages(class_id, limit=80)
    return templates.TemplateResponse(
        request, "class_room.html",
        ctx(request, user, cls=cls, role=role, members=members, messages=messages),
    )


# ---------- poll ----------
@app.post("/api/poll/{class_id}")
async def api_poll(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    cls = get_class_by_id(class_id)
    if not cls:
        return JSONResponse({"error": "not found"}, status_code=404)
    msgs = get_messages(class_id, limit=80)
    return JSONResponse({
        "blackboard": cls["blackboard"] or "",
        "stage": cls["stage"] if "stage" in cls.keys() else 0,
        "messages": [
            {"id": m["id"], "type": m["sender_type"], "name": m["sender_name"], "content": m["content"]}
            for m in msgs
        ],
    })


# ---------- blackboard ----------
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


# ---------- upload ----------
@app.post("/api/upload/{class_id}")
async def api_upload(request: Request, class_id: int, file: UploadFile = File(...)):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return JSONResponse({"error": "unsupported file type"}, status_code=400)

    safe_name = f"c{class_id}_{random.randint(10000, 99999)}{ext}"
    path = os.path.join("static", "uploads", safe_name)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    url = f"/static/uploads/{safe_name}"
    return JSONResponse({"ok": True, "url": url})


# ---------- stage ----------
@app.post("/api/stage/{class_id}/{action}")
async def api_stage(request: Request, class_id: int, action: str):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if get_role(class_id, user["id"]) != "teacher":
        return JSONResponse({"error": "teachers only"}, status_code=403)
    cls = get_class_by_id(class_id)
    cur = cls["stage"] or 0
    lang = user["lang"] or "ja"
    total = len(stage_list(lang))
    if action == "next":
        cur = min(cur + 1, total - 1)
    elif action == "prev":
        cur = max(cur - 1, 0)
    set_stage(class_id, cur)
    return JSONResponse({"ok": True, "stage": cur})


# ---------- announce ----------
@app.post("/api/announce/{class_id}")
async def api_announce(request: Request, class_id: int):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    role = get_role(class_id, user["id"])
    if not role:
        return JSONResponse({"error": "not member"}, status_code=403)
    data = await request.json()
    text = (data.get("message") or "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)
    add_message(class_id, "user", user["name"], text)
    return JSONResponse({"ok": True})


# ---------- history ----------
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
            {
                "id": r["id"],
                "content": r["content"] or "",
                "author": r["author"] or "",
                "created_at": r["created_at"],
            }
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


# ---------- dev ----------
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
    html = f"""<!DOCTYPE html>
<html><body>
<script>
  sessionStorage.setItem('uid', '{uid}');
  location.replace('/dashboard?uid={uid}');
</script>
</body></html>"""
    return HTMLResponse(html)


@app.post("/dev/delete/{uid}")
def dev_delete(request: Request, uid: int):
    delete_user(uid)
    return RedirectResponse("/dev/users", status_code=303)