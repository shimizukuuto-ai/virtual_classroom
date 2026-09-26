import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "classroom.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        lang TEXT NOT NULL DEFAULT 'ja',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        subject TEXT NOT NULL,
        description TEXT,
        teacher_id INTEGER NOT NULL,
        join_code TEXT NOT NULL UNIQUE,
        is_public INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        joined_at TEXT NOT NULL,
        UNIQUE(class_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS join_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        UNIQUE(class_id, user_id)
    );
        CREATE TABLE IF NOT EXISTS blackboard_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        content TEXT,
        author TEXT,
        created_at TEXT NOT NULL
    );
    """)
    for ddl in [
        "ALTER TABLE classes ADD COLUMN blackboard TEXT DEFAULT ''",
        "ALTER TABLE classes ADD COLUMN ai_mode INTEGER DEFAULT 0",
        "ALTER TABLE classes ADD COLUMN stage INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'ja'",
        "ALTER TABLE classes ADD COLUMN is_public INTEGER DEFAULT 1",
        "ALTER TABLE classes ADD COLUMN ai_teacher_mode INTEGER DEFAULT 0",
        "ALTER TABLE classes ADD COLUMN teaching_focus TEXT DEFAULT ''",
        "ALTER TABLE classes ADD COLUMN taught_by TEXT DEFAULT ''",
    ]:
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- users ----------
def create_user(name, lang="ja"):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (name, lang, created_at) VALUES (?, ?, ?)",
            (name, lang, now()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return None
    uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return uid


def get_user_by_name(name):
    conn = get_conn()
    r = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
    conn.close()
    return r


def get_user_by_id(uid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return r


def set_user_lang(uid, lang):
    conn = get_conn()
    conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, uid))
    conn.commit()
    conn.close()


def list_all_users(limit=200):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def delete_user(uid):
    conn = get_conn()
    conn.execute("DELETE FROM enrollments WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM join_requests WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()


# ---------- classes ----------
def create_class(title, subject, description, teacher_id, join_code, is_public=1,
                 ai_teacher_mode=0, teaching_focus="", taught_by=""):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO classes
               (title, subject, description, teacher_id, join_code, is_public, created_at,
                blackboard, ai_mode, stage, ai_teacher_mode, teaching_focus, taught_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, '', 0, 0, ?, ?, ?)""",
            (title, subject, description, teacher_id, join_code, is_public, now(),
             ai_teacher_mode, teaching_focus, taught_by),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return None
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO enrollments (class_id, user_id, role, joined_at) VALUES (?, ?, 'teacher', ?)",
        (cid, teacher_id, now()),
    )
    conn.commit()
    conn.close()
    return cid


def get_class_by_code(code):
    conn = get_conn()
    r = conn.execute("SELECT * FROM classes WHERE join_code = ?", (code,)).fetchone()
    conn.close()
    return r


def get_class_by_id(cid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM classes WHERE id = ?", (cid,)).fetchone()
    conn.close()
    return r


def list_public_classes(query=""):
    conn = get_conn()
    if query:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT c.*, u.name AS teacher_name FROM classes c
               JOIN users u ON u.id = c.teacher_id
               WHERE c.is_public = 1
                 AND (c.title LIKE ? OR c.subject LIKE ? OR c.description LIKE ?)
               ORDER BY c.created_at DESC LIMIT 50""",
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT c.*, u.name AS teacher_name FROM classes c
               JOIN users u ON u.id = c.teacher_id
               WHERE c.is_public = 1
               ORDER BY c.created_at DESC LIMIT 50"""
        ).fetchall()
    conn.close()
    return rows


def count_students(class_id):
    conn = get_conn()
    r = conn.execute(
        "SELECT COUNT(*) AS n FROM enrollments WHERE class_id = ? AND role = 'student'",
        (class_id,),
    ).fetchone()
    conn.close()
    return r["n"] if r else 0


def join_class(class_id, user_id, role="student"):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO enrollments (class_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
            (class_id, user_id, role, now()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False
    conn.close()
    return True


def list_classes_for_user(user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, e.role FROM classes c
        JOIN enrollments e ON e.class_id = c.id
        WHERE e.user_id = ?
        ORDER BY c.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return rows


def list_members(class_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.name, e.role FROM enrollments e
        JOIN users u ON u.id = e.user_id
        WHERE e.class_id = ?
        ORDER BY e.joined_at
    """, (class_id,)).fetchall()
    conn.close()
    return rows


def get_role(class_id, user_id):
    conn = get_conn()
    r = conn.execute(
        "SELECT role FROM enrollments WHERE class_id = ? AND user_id = ?",
        (class_id, user_id),
    ).fetchone()
    conn.close()
    return r["role"] if r else None


def set_blackboard(class_id, text):
    conn = get_conn()
    conn.execute("UPDATE classes SET blackboard = ? WHERE id = ?", (text, class_id))
    conn.commit()
    conn.close()


def set_ai_mode(class_id, on):
    conn = get_conn()
    conn.execute(
        "UPDATE classes SET ai_mode = ? WHERE id = ?",
        (1 if on else 0, class_id),
    )
    conn.commit()
    conn.close()


def set_stage(class_id, stage):
    conn = get_conn()
    conn.execute("UPDATE classes SET stage = ? WHERE id = ?", (stage, class_id))
    conn.commit()
    conn.close()


# ---------- messages ----------
def add_message(class_id, sender_type, sender_name, content):
    conn = get_conn()
    conn.execute(
        """INSERT INTO messages
           (class_id, sender_type, sender_name, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (class_id, sender_type, sender_name, content, now()),
    )
    conn.commit()
    conn.close()


def get_messages(class_id, limit=80):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE class_id = ? ORDER BY id ASC LIMIT ?",
        (class_id, limit),
    ).fetchall()
    conn.close()
    return rows


# ---------- join requests ----------
def create_join_request(class_id, user_id):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO join_requests (class_id, user_id, status, created_at) VALUES (?, ?, 'pending', ?)",
            (class_id, user_id, now()),
        )
        conn.commit()
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return rid
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE join_requests SET status='pending' WHERE class_id=? AND user_id=?",
            (class_id, user_id),
        )
        conn.commit()
        conn.close()
        return None


def list_pending_requests_for_teacher(teacher_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, u.name AS user_name, c.title AS class_title, c.id AS class_id
        FROM join_requests r
        JOIN users u ON u.id = r.user_id
        JOIN classes c ON c.id = r.class_id
        WHERE c.teacher_id = ? AND r.status = 'pending'
        ORDER BY r.created_at DESC
    """, (teacher_id,)).fetchall()
    conn.close()
    return rows


def get_request_by_id(rid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM join_requests WHERE id = ?", (rid,)).fetchone()
    conn.close()
    return r


def set_request_status(rid, status):
    conn = get_conn()
    conn.execute("UPDATE join_requests SET status = ? WHERE id = ?", (status, rid))
    conn.commit()
    conn.close()


def count_pending_for_teacher(teacher_id):
    conn = get_conn()
    r = conn.execute("""
        SELECT COUNT(*) AS n FROM join_requests r
        JOIN classes c ON c.id = r.class_id
        WHERE c.teacher_id = ? AND r.status = 'pending'
    """, (teacher_id,)).fetchone()
    conn.close()
    return r["n"] if r else 0


def list_my_requests(user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, c.title AS class_title
        FROM join_requests r
        JOIN classes c ON c.id = r.class_id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return rows

    # ---------- blackboard history ----------
def save_blackboard_history(class_id, content, author):
    conn = get_conn()
    conn.execute(
        """INSERT INTO blackboard_history (class_id, content, author, created_at)
           VALUES (?, ?, ?, ?)""",
        (class_id, content or "", author or "", now()),
    )
    conn.commit()
    conn.close()


def list_blackboard_history(class_id, limit=50):
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM blackboard_history
           WHERE class_id = ? ORDER BY id DESC LIMIT ?""",
        (class_id, limit),
    ).fetchall()
    conn.close()
    return rows


def get_blackboard_history_by_id(hid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM blackboard_history WHERE id = ?", (hid,)).fetchone()
    conn.close()
    return r