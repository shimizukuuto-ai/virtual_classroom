
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from db import get_conn, get_class_by_id, get_role, get_user_by_id, is_banned

router = APIRouter(prefix="/api/social")


def initialize():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS social_shared_notes (
                id BIGSERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_shared_notes_room
            ON social_shared_notes(class_id, id DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS social_reflections (
                id BIGSERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_reflections_owner
            ON social_reflections(class_id, user_id, id DESC)
        """)


def authorize(request, class_id):
    uid = request.session.get("user_id")
    if not uid:
        return None, JSONResponse(
            {"error": "login required"}, status_code=401
        )

    user = get_user_by_id(int(uid))
    cls = get_class_by_id(class_id)

    if not user or not cls or (cls.get("room_type") or "class") != "social":
        return None, JSONResponse(
            {"error": "room not found"}, status_code=404
        )

    if not get_role(class_id, user["id"]) or is_banned(class_id, user["id"]):
        return None, JSONResponse(
            {"error": "not a member"}, status_code=403
        )

    return user, None


@router.get("/{class_id}/notes")
def get_notes(request: Request, class_id: int):
    user, error = authorize(request, class_id)
    if error is not None:
        return error

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, author_name, content,
              to_char(created_at AT TIME ZONE 'UTC',
                      'YYYY-MM-DD HH24:MI') AS created_at
            FROM social_shared_notes
            WHERE class_id = %s
            ORDER BY id DESC
            LIMIT 100
        """, (class_id,)).fetchall()

    return {"items": list(reversed([dict(r) for r in rows]))}


@router.post("/{class_id}/notes")
async def add_note(request: Request, class_id: int):
    user, error = authorize(request, class_id)
    if error is not None:
        return error

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    content = str(data.get("content") or "").strip()

    if not 1 <= len(content) <= 2000:
        return JSONResponse(
            {"error": "content must be 1-2000 characters"},
            status_code=400
        )

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO social_shared_notes
                (class_id, author_id, author_name, content)
            VALUES (%s, %s, %s, %s)
        """, (class_id, user["id"], user["name"], content))

    return {"ok": True}


@router.get("/{class_id}/reflections")
def get_reflections(request: Request, class_id: int):
    user, error = authorize(request, class_id)
    if error is not None:
        return error

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, content,
              to_char(created_at AT TIME ZONE 'UTC',
                      'YYYY-MM-DD HH24:MI') AS created_at
            FROM social_reflections
            WHERE class_id = %s AND user_id = %s
            ORDER BY id DESC
            LIMIT 100
        """, (class_id, user["id"])).fetchall()

    return {"items": [dict(r) for r in rows]}


@router.post("/{class_id}/reflections")
async def add_reflection(request: Request, class_id: int):
    user, error = authorize(request, class_id)
    if error is not None:
        return error

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    content = str(data.get("content") or "").strip()

    if not 1 <= len(content) <= 4000:
        return JSONResponse(
            {"error": "content must be 1-4000 characters"},
            status_code=400
        )

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO social_reflections
                (class_id, user_id, content)
            VALUES (%s, %s, %s)
        """, (class_id, user["id"], content))

    return {"ok": True}
