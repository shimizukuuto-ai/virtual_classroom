
# VC_SESSIONS_V1
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from html import escape

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg.rows import dict_row

from db import (
    get_conn,
    get_class_by_id,
    get_role,
    list_classes_taught_by,
    is_banned,
)

router = APIRouter()


def initialize():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS vc_lesson_sessions (
                    id BIGSERIAL PRIMARY KEY,
                    class_id INTEGER NOT NULL
                        REFERENCES classes(id) ON DELETE CASCADE,
                    starts_at TIMESTAMPTZ NOT NULL,
                    duration_min INTEGER NOT NULL DEFAULT 30,
                    capacity INTEGER NOT NULL DEFAULT 30,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (duration_min BETWEEN 15 AND 240),
                    CHECK (capacity BETWEEN 1 AND 200),
                    CHECK (status IN (
                        'scheduled', 'live',
                        'completed', 'cancelled'
                    ))
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS vc_lesson_rsvps (
                    session_id BIGINT NOT NULL
                        REFERENCES vc_lesson_sessions(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (session_id, user_id)
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS vc_sessions_by_start
                ON vc_lesson_sessions(starts_at)
            """)
        conn.commit()


def current(request):
    from main import current_user
    return current_user(request)


def is_ja(user):
    return (user.get("lang") or "en") == "ja"


def t(ja, en, lang):
    return ja if lang else en


def page(title, content, ja=False):
    language = "ja" if ja else "en"
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | Virtual Classroom</title>
<style>
* {{ box-sizing:border-box }}
body {{
    margin:0;
    background:#0d1424;
    color:#eef2ff;
    font-family:system-ui,-apple-system,sans-serif;
}}
main {{ max-width:1000px;margin:auto;padding:25px }}
a {{ color:#9bbcff }}
h1 {{ font-size:28px }}
.card {{
    background:#19243b;
    border:1px solid #35425d;
    border-radius:16px;
    padding:20px;
    margin:15px 0;
}}
.grid {{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(270px,1fr));
    gap:15px;
}}
button,.btn {{
    background:#526df5;
    color:white;
    padding:11px 16px;
    border:0;
    border-radius:9px;
    cursor:pointer;
    text-decoration:none;
    display:inline-block;
    margin:5px 0;
}}
input,select {{
    background:#101b31;
    color:white;
    border:1px solid #596781;
    padding:10px;
    border-radius:8px;
    max-width:100%;
}}
label {{ display:block;margin:12px 0 }}
form {{ margin:8px 0 }}
.live {{ color:#5aee9b;font-weight:bold }}
.soon {{ color:#ffcc74;font-weight:bold }}
.muted {{ color:#abb9d1 }}
</style>
</head>
<body>
<main>
<p>
<a href="/dashboard">Dashboard</a> ·
<a href="/classes">Classrooms</a> ·
<a href="/sessions">Lessons</a>
</p>
{content}
</main>
</body>
</html>
""")


def safe_post(request):
    origin = request.headers.get("origin")
    if not origin:
        return True
    from urllib.parse import urlsplit
    try:
        a = urlsplit(origin)
        b = urlsplit(str(request.base_url))
        return (a.scheme, a.netloc) == (b.scheme, b.netloc)
    except ValueError:
        return False


def action_button(path, label):
    return (
        f'<form method="post" action="{escape(path, quote=True)}">'
        f'<button>{escape(label)}</button></form>'
    )


def session_by_id(sid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                SELECT s.*, cl.title, cl.subject,
                       cl.teacher_id, cl.is_public
                FROM vc_lesson_sessions s
                JOIN classes cl ON cl.id=s.class_id
                WHERE s.id=%s
            """, (sid,))
            return c.fetchone()


@router.get("/sessions")
def sessions_page(request: Request):
    user = current(request)
    if not user:
        return RedirectResponse("/login")

    ja = is_ja(user)
    now = datetime.now(timezone.utc)

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                SELECT s.*, cl.title, cl.subject,
                       COALESCE(u.display_name,u.name) AS teacher_name,
                       (SELECT COUNT(*)
                        FROM vc_lesson_rsvps r
                        WHERE r.session_id=s.id) AS reserved
                FROM vc_lesson_sessions s
                JOIN classes cl ON cl.id=s.class_id
                JOIN users u ON u.id=cl.teacher_id
                WHERE cl.is_public IN (1,2)
                  AND s.status IN ('scheduled','live')
                ORDER BY
                    CASE WHEN s.status='live' THEN 0 ELSE 1 END,
                    s.starts_at
                LIMIT 80
            """)
            lessons = c.fetchall()

    cards = []

    for s in lessons:
        start = s["starts_at"].astimezone(timezone.utc)

        if s["status"] == "live":
            status = "● LIVE"
            css = "live"
        elif start <= now + timedelta(minutes=15):
            status = t("まもなく開始・先生待ち", "Starting soon / Waiting", ja)
            css = "soon"
        else:
            status = t("開催予定", "Scheduled", ja)
            css = "muted"

        sid = int(s["id"])
        date = start.strftime("%Y-%m-%d %H:%M UTC")

        cards.append(f"""
        <div class="card">
            <p class="{css}">{escape(status)}</p>
            <h2>{escape(s["title"])}</h2>
            <p>{escape(s["subject"])}</p>
            <p>{escape(s["teacher_name"])}</p>
            <p>{date}</p>
            <p>{s["duration_min"]} min</p>
            <p>{s["reserved"]}/{s["capacity"]}
               {t("人が参加予定","RSVPs",ja)}</p>
            <a class="btn" href="/sessions/{sid}">
                {t("詳細・参加予定","Details / RSVP",ja)}
            </a>
        </div>
        """)

    own = list_classes_taught_by(user["id"])

    options = "".join(
        f'<option value="{int(cl["id"])}">{escape(cl["title"])}</option>'
        for cl in own
        if (cl.get("room_type") or "class") != "study"
    )

    creation = ""

    if options:
        creation = f"""
        <div class="card">
        <h2>{t("先生：授業を開催予約","Teacher: Schedule a lesson",ja)}</h2>

        <form method="post" action="/sessions/create">
            <label>{t("教室","Classroom",ja)}
                <select name="class_id" required>{options}</select>
            </label>

            <label>{t("開催日時","Start date and time",ja)}
                <input type="datetime-local"
                       name="starts_at" required>
            </label>

            <label>{t("タイムゾーン","Timezone",ja)}
                <input name="tz"
                       value="Asia/Tokyo" required>
            </label>

            <label>{t("授業時間（分）","Duration (minutes)",ja)}
                <input type="number" name="duration"
                       value="30" min="15" max="240">
            </label>

            <label>{t("定員","Capacity",ja)}
                <input type="number" name="capacity"
                       value="30" min="1" max="200">
            </label>

            <button>{t("授業を予約","Schedule lesson",ja)}</button>
        </form>
        </div>
        """

    body = f"""
    <h1>{t("授業を探す","Find lessons",ja)}</h1>
    <p class="muted">
    {t("常設教室は今までどおり利用できます。日時はUTC表示です。",
       "Permanent classrooms remain available. Times are UTC.",ja)}
    </p>
    <div class="grid">
    {''.join(cards) or t("開催予定はまだありません。","No lessons yet.",ja)}
    </div>
    {creation}
    """

    return page(t("授業を探す","Find lessons",ja), body, ja)


@router.post("/sessions/create")
def create_session(
    request: Request,
    class_id: int = Form(...),
    starts_at: str = Form(...),
    tz: str = Form("Asia/Tokyo"),
    duration: int = Form(30),
    capacity: int = Form(30),
):
    user = current(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if not safe_post(request):
        return HTMLResponse("Invalid origin", status_code=403)

    cl = get_class_by_id(class_id)

    if not cl or int(cl["teacher_id"]) != int(user["id"]):
        return HTMLResponse("Forbidden", status_code=403)

    if get_role(class_id, user["id"]) != "teacher":
        return HTMLResponse("Forbidden", status_code=403)

    if not (15 <= duration <= 240 and 1 <= capacity <= 200):
        return HTMLResponse("Invalid duration or capacity", status_code=400)

    try:
        zone = ZoneInfo(tz.strip())
        naive = datetime.fromisoformat(starts_at)

        if naive.tzinfo is not None:
            raise ValueError("Expected local time")

        local = naive.replace(tzinfo=zone)
        start = local.astimezone(timezone.utc)

        if start.astimezone(zone).replace(tzinfo=None) != naive:
            raise ValueError("Invalid local time")

        if not datetime.now(timezone.utc) < start <= datetime.now(timezone.utc) + timedelta(days=365):
            raise ValueError("Date outside allowed range")

    except (ValueError, ZoneInfoNotFoundError, OverflowError):
        return HTMLResponse("Invalid date or timezone", status_code=400)

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                INSERT INTO vc_lesson_sessions
                    (class_id,starts_at,duration_min,capacity)
                VALUES (%s,%s,%s,%s)
                RETURNING id
            """, (class_id, start, duration, capacity))

            sid = c.fetchone()["id"]
        conn.commit()

    return RedirectResponse(f"/sessions/{sid}", status_code=303)


@router.get("/sessions/{sid}")
def session_detail(request: Request, sid: int):
    user = current(request)

    if not user:
        return RedirectResponse("/login")

    s = session_by_id(sid)

    if not s:
        return HTMLResponse("Not found", status_code=404)

    role = get_role(s["class_id"], user["id"])

    if int(s["is_public"]) not in (1,2) and not role:
        return HTMLResponse("Forbidden", status_code=403)

    if is_banned(s["class_id"], user["id"]):
        return HTMLResponse("Forbidden", status_code=403)

    ja = is_ja(user)

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                SELECT COUNT(*) AS n
                FROM vc_lesson_rsvps
                WHERE session_id=%s
            """, (sid,))
            count = c.fetchone()["n"]

            c.execute("""
                SELECT 1 FROM vc_lesson_rsvps
                WHERE session_id=%s AND user_id=%s
            """, (sid, user["id"]))
            reserved = c.fetchone() is not None

    teacher = (
        int(s["teacher_id"]) == int(user["id"])
        and role == "teacher"
    )

    buttons = ""
    status = s["status"]

    if teacher:
        if status == "scheduled":
            buttons += action_button(
                f"/sessions/{sid}/start",
                t("授業を開始（LIVE）","Start LIVE",ja)
            )
            buttons += action_button(
                f"/sessions/{sid}/cancel",
                t("授業を中止","Cancel lesson",ja)
            )

        if status == "live":
            buttons += action_button(
                f"/sessions/{sid}/finish",
                t("授業を終了","Finish lesson",ja)
            )

    elif status in ("scheduled", "live"):
        if reserved:
            buttons += action_button(
                f"/sessions/{sid}/unrsvp",
                t("参加予定を解除","Cancel RSVP",ja)
            )
        else:
            buttons += action_button(
                f"/sessions/{sid}/rsvp",
                t("参加予定に登録","RSVP",ja)
            )

    if role:
        buttons += (
            f'<a class="btn" href="/class/{int(s["class_id"])}">'
            f'{t("教室に入る","Enter classroom",ja)}</a>'
        )
    elif int(s["is_public"]) == 2:
        buttons += (
            f'<a class="btn" href="/classes/{int(s["class_id"])}/open">'
            f'{t("教室に参加","Join classroom",ja)}</a>'
        )
    else:
        buttons += '<a href="/classes">Request classroom access</a>'

    date = s["starts_at"].astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    body = f"""
    <h1>{escape(s["title"])}</h1>
    <div class="card">
        <p>{escape(s["subject"])}</p>
        <h2>{escape(status.upper())}</h2>
        <p>{date}</p>
        <p>{s["duration_min"]} min</p>
        <p>{count}/{s["capacity"]}
           {t("参加予定","RSVPs",ja)}</p>
        {buttons}
    </div>
    <p class="muted">
    {t("授業は先生が開始操作をするとLIVEになります。",
       "The lesson becomes LIVE when the teacher starts it.",ja)}
    </p>
    """

    return page(s["title"], body, ja)


@router.post("/sessions/{sid}/rsvp")
def rsvp(request: Request, sid: int):
    user = current(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if not safe_post(request):
        return HTMLResponse("Invalid origin", status_code=403)

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                SELECT s.*,cl.is_public
                FROM vc_lesson_sessions s
                JOIN classes cl ON cl.id=s.class_id
                WHERE s.id=%s
                FOR UPDATE OF s
            """, (sid,))

            s = c.fetchone()

            if not s or s["status"] not in ("scheduled", "live"):
                return HTMLResponse("Not available", status_code=404)

            role = get_role(s["class_id"], user["id"])

            if int(s["is_public"]) not in (1,2) and not role:
                return HTMLResponse("Forbidden", status_code=403)

            if is_banned(s["class_id"], user["id"]):
                return HTMLResponse("Forbidden", status_code=403)

            c.execute("""
                SELECT 1 FROM vc_lesson_rsvps
                WHERE session_id=%s AND user_id=%s
            """, (sid, user["id"]))

            if not c.fetchone():
                c.execute("""
                    SELECT COUNT(*) AS n
                    FROM vc_lesson_rsvps
                    WHERE session_id=%s
                """, (sid,))

                if c.fetchone()["n"] >= s["capacity"]:
                    return HTMLResponse("Lesson full", status_code=409)

                c.execute("""
                    INSERT INTO vc_lesson_rsvps(session_id,user_id)
                    VALUES (%s,%s)
                """, (sid, user["id"]))

        conn.commit()

    return RedirectResponse(f"/sessions/{sid}", status_code=303)


@router.post("/sessions/{sid}/unrsvp")
def unrsvp(request: Request, sid: int):
    user = current(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if not safe_post(request):
        return HTMLResponse("Invalid origin", status_code=403)

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                DELETE FROM vc_lesson_rsvps
                WHERE session_id=%s AND user_id=%s
            """, (sid, user["id"]))
        conn.commit()

    return RedirectResponse(f"/sessions/{sid}", status_code=303)


@router.post("/sessions/{sid}/{action}")
def teacher_action(request: Request, sid: int, action: str):
    user = current(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if not safe_post(request):
        return HTMLResponse("Invalid origin", status_code=403)

    if action not in ("start", "finish", "cancel"):
        return HTMLResponse("Not found", status_code=404)

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                SELECT s.*,cl.teacher_id
                FROM vc_lesson_sessions s
                JOIN classes cl ON cl.id=s.class_id
                WHERE s.id=%s
                FOR UPDATE OF s
            """, (sid,))

            s = c.fetchone()

            if not s:
                return HTMLResponse("Not found", status_code=404)

            if int(s["teacher_id"]) != int(user["id"]):
                return HTMLResponse("Forbidden", status_code=403)

            if get_role(s["class_id"], user["id"]) != "teacher":
                return HTMLResponse("Forbidden", status_code=403)

            expected = {
                "start": "scheduled",
                "finish": "live",
                "cancel": "scheduled",
            }[action]

            if s["status"] != expected:
                return HTMLResponse("Invalid state", status_code=409)

            new_status = {
                "start": "live",
                "finish": "completed",
                "cancel": "cancelled",
            }[action]

            c.execute("""
                UPDATE vc_lesson_sessions
                SET status=%s
                WHERE id=%s
            """, (new_status, sid))

        conn.commit()

    return RedirectResponse(f"/sessions/{sid}", status_code=303)
