import os
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=3,
            max_size=10,
            open=True,
            timeout=10,
        )
    return _pool


def get_conn():
    return get_pool().connection()


def init_pool():
    pool = get_pool()
    pool.open()
    init_db()


def close_pool():
    if _pool:
        _pool.close()


def now():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return datetime.now().strftime("%Y-%m-%d")


# ============================================================
# バッジ / スキン / ランク定義
# ============================================================
BADGES = {
    "first_class":     ("初授業", "First Class", "最初のクラスを開いた", "Taught your first class"),
    "class_10":        ("常連講師", "Regular", "10クラス開講", "Taught 10 classes"),
    "class_50":        ("講師の鑑", "Master Teacher", "50クラス開講", "Taught 50 classes"),
    "first_answer":    ("初回答", "First Answer", "Q&Aに初回答", "Answered your first question"),
    "answer_20":       ("賢者", "Wise One", "Q&Aに20回答", "Answered 20 questions"),
    "helpful_10":      ("役立つ人", "Helpful", "役に立った10回", "10 helpful votes"),
    "helpful_100":     ("頼れる存在", "Trusted", "役に立った100回", "100 helpful votes"),
    "streak_3":        ("三日坊主返上", "3-Day Streak", "3日連続参加", "3-day streak"),
    "streak_7":        ("一週間の習慣", "7-Day Streak", "7日連続参加", "7-day streak"),
    "streak_30":       ("皆勤賞", "Perfect Month", "30日連続参加", "30-day streak"),
    "first_weekly":    ("週次デビュー", "Weekly Debut", "初の週次公開授業", "Hosted first weekly class"),
    "weekly_10":       ("週次マスター", "Weekly Master", "週次公開授業10回", "Hosted 10 weekly classes"),
    "students_10":     ("10人の先生", "10 Students", "累計10人の生徒", "Taught 10 students total"),
    "students_100":    ("100人の先生", "100 Students", "累計100人の生徒", "Taught 100 students total"),
}

SKINS = {
    "default":  ("標準", "Default", 0, "0x3b82f6"),
    "glasses":  ("眼鏡", "Glasses", 100, "0x6366f1"),
    "hat":      ("帽子", "Hat", 300, "0xf59e0b"),
    "robe":     ("ローブ", "Robe", 800, "0x8b5cf6"),
    "crown":    ("王冠", "Crown", 2000, "0xfbbf24"),
    "aura":     ("オーラ", "Aura", 5000, "0xef4444"),
}

RANKS = [
    ("novice",     0,    "新人",     "Novice",        "#94a3b8"),
    ("apprentice", 100,  "見習い",   "Apprentice",    "#10b981"),
    ("teacher",    300,  "教師",     "Teacher",       "#3b82f6"),
    ("senior",     800,  "上級教師", "Senior Teacher","#8b5cf6"),
    ("master",     2000, "達人",     "Master",        "#f59e0b"),
    ("legend",     5000, "伝説",     "Legend",        "#ef4444"),
]


def rank_for_xp(xp):
    r = RANKS[0]
    for entry in RANKS:
        if xp >= entry[1]:
            r = entry
    return r


def next_rank(xp):
    for entry in RANKS:
        if xp < entry[1]:
            return entry
    return None


# ============================================================
# 初期化
# ============================================================
def init_db():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                email TEXT UNIQUE,
                lang TEXT NOT NULL DEFAULT 'ja',
                title TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                skin TEXT DEFAULT 'default',
                bonus_xp INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS magic_tokens (
                id SERIAL PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT,
                teacher_id INTEGER NOT NULL,
                join_code TEXT NOT NULL UNIQUE,
                is_public INTEGER NOT NULL DEFAULT 1,
                blackboard TEXT DEFAULT '',
                stage INTEGER DEFAULT 0,
                taught_by TEXT DEFAULT '',
                is_weekly INTEGER DEFAULT 0,
                weekly_time TEXT DEFAULT '',
                next_session TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS class_steps (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                UNIQUE(class_id, user_id)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                sender_type TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                content TEXT NOT NULL,
                helpful_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS message_helpful (
                id SERIAL PRIMARY KEY,
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(message_id, user_id)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS join_requests (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                UNIQUE(class_id, user_id)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS blackboard_history (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                content TEXT,
                author TEXT,
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS class_bans (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(class_id, user_id)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                is_anonymous INTEGER DEFAULT 1,
                asked_by INTEGER,
                answered_by INTEGER,
                answer TEXT,
                answered_at TEXT,
                created_at TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                badge_key TEXT NOT NULL,
                earned_at TEXT NOT NULL,
                UNIQUE(user_id, badge_key)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                UNIQUE(user_id, class_id, date)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS learning_cards (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
        conn.commit()


# ============================================================
# users
# ============================================================
def create_user(name, email=None, lang="ja"):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            try:
                c.execute(
                    "INSERT INTO users (name, email, lang, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                    (name, email, lang, now()),
                )
                uid = c.fetchone()["id"]
                conn.commit()
                return uid
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return None


def get_user_by_name(name):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM users WHERE name = %s", (name,))
            return c.fetchone()


def get_user_by_email(email):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM users WHERE email = %s", (email,))
            return c.fetchone()


def get_user_by_id(uid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM users WHERE id = %s", (uid,))
            return c.fetchone()


def set_user_lang(uid, lang):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET lang = %s WHERE id = %s", (lang, uid))
        conn.commit()


def update_user_profile(uid, title, bio):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET title = %s, bio = %s WHERE id = %s",
                (title or "", bio or "", uid),
            )
        conn.commit()


def set_user_skin(uid, skin_key):
    if skin_key not in SKINS:
        return False
    xp = calc_xp(uid)
    if xp < SKINS[skin_key][2]:
        return False
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET skin = %s WHERE id = %s", (skin_key, uid))
        conn.commit()
    return True


def add_bonus_xp(uid, amount):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET bonus_xp = COALESCE(bonus_xp, 0) + %s WHERE id = %s",
                (int(amount), uid),
            )
        conn.commit()
    check_badges(uid)
    return True


def reset_bonus_xp(uid):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET bonus_xp = 0 WHERE id = %s", (uid,))
        conn.commit()


def list_all_users(limit=200):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM users ORDER BY id DESC LIMIT %s", (limit,))
            return c.fetchall()


def delete_user(uid):
    with get_conn() as conn:
        with conn.cursor() as c:
            for t in ("enrollments", "join_requests", "class_bans",
                      "user_badges", "attendance", "learning_cards"):
                c.execute(f"DELETE FROM {t} WHERE user_id = %s", (uid,))
            c.execute("DELETE FROM users WHERE id = %s", (uid,))
        conn.commit()


# ============================================================
# magic tokens
# ============================================================
def create_magic_token(token_hash, email, expires_at):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO magic_tokens (token_hash, email, expires_at, created_at) VALUES (%s, %s, %s, %s)",
                (token_hash, email, expires_at, now()),
            )
        conn.commit()


def get_magic_token(token_hash):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM magic_tokens WHERE token_hash = %s", (token_hash,))
            return c.fetchone()


def use_magic_token(token_hash):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE magic_tokens SET used_at = %s WHERE token_hash = %s AND used_at IS NULL",
                (now(), token_hash),
            )
            ok = c.rowcount > 0
        conn.commit()
        return ok


# ============================================================
# stats / XP / rank
# ============================================================
def user_stats(uid):
    user = get_user_by_id(uid)
    if not user:
        return None
    name = user["name"]
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
            SELECT
              (SELECT COALESCE(SUM(helpful_count),0) FROM messages
                WHERE sender_name = %s AND sender_type = 'user') AS helpful,
              (SELECT COUNT(*) FROM messages
                WHERE sender_name = %s AND sender_type = 'user') AS msg_count,
              (SELECT COUNT(*) FROM classes WHERE teacher_id = %s) AS taught,
              (SELECT COUNT(*) FROM classes WHERE teacher_id = %s AND is_weekly = 1) AS weekly_hosted,
              (SELECT COUNT(*) FROM enrollments WHERE user_id = %s AND role = 'student') AS joined,
              (SELECT COUNT(*) FROM questions WHERE answered_by = %s) AS answers,
              (SELECT COUNT(*) FROM enrollments e
                JOIN classes c ON c.id = e.class_id
                WHERE c.teacher_id = %s AND e.role = 'student') AS students_total
            """, (name, name, uid, uid, uid, uid, uid))
            row = c.fetchone()
    bonus = user["bonus_xp"] if "bonus_xp" in user.keys() and user["bonus_xp"] is not None else 0
    xp = (row["helpful"] * 5 + row["answers"] * 20 + row["taught"] * 50
          + row["weekly_hosted"] * 30 + row["students_total"] * 2 + bonus)
    return {
        "helpful": row["helpful"],
        "messages": row["msg_count"],
        "taught": row["taught"],
        "joined": row["joined"],
        "answers": row["answers"],
        "weekly_hosted": row["weekly_hosted"],
        "students_total": row["students_total"],
        "xp": xp,
        "rank": rank_for_xp(xp),
        "next_rank": next_rank(xp),
    }


def calc_xp(uid):
    s = user_stats(uid)
    return s["xp"] if s else 0


def calc_streak(uid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT DISTINCT date FROM attendance WHERE user_id = %s ORDER BY date DESC LIMIT 60",
                (uid,),
            )
            rows = c.fetchall()
    if not rows:
        return 0
    streak = 0
    expected = datetime.now().date()
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d == expected:
            streak += 1
            expected = expected - timedelta(days=1)
        elif d == expected - timedelta(days=1) and streak == 0:
            streak += 1
            expected = d - timedelta(days=1)
        else:
            break
    return streak


def record_attendance(uid, class_id):
    with get_conn() as conn:
        with conn.cursor() as c:
            try:
                c.execute(
                    "INSERT INTO attendance (user_id, class_id, date) VALUES (%s, %s, %s)",
                    (uid, class_id, today()),
                )
                conn.commit()
                return True
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return False


# ============================================================
# badges
# ============================================================
def list_user_badges(uid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT * FROM user_badges WHERE user_id = %s ORDER BY earned_at DESC",
                (uid,),
            )
            return c.fetchall()


def grant_badge(uid, key):
    if key not in BADGES:
        return False
    with get_conn() as conn:
        with conn.cursor() as c:
            try:
                c.execute(
                    "INSERT INTO user_badges (user_id, badge_key, earned_at) VALUES (%s, %s, %s)",
                    (uid, key, now()),
                )
                conn.commit()
                return True
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return False


def check_badges(uid):
    s = user_stats(uid)
    if not s:
        return
    streak = calc_streak(uid)
    conds = [
        ("first_class", s["taught"] >= 1),
        ("class_10", s["taught"] >= 10),
        ("class_50", s["taught"] >= 50),
        ("first_answer", s["answers"] >= 1),
        ("answer_20", s["answers"] >= 20),
        ("helpful_10", s["helpful"] >= 10),
        ("helpful_100", s["helpful"] >= 100),
        ("streak_3", streak >= 3),
        ("streak_7", streak >= 7),
        ("streak_30", streak >= 30),
        ("first_weekly", s["weekly_hosted"] >= 1),
        ("weekly_10", s["weekly_hosted"] >= 10),
        ("students_10", s["students_total"] >= 10),
        ("students_100", s["students_total"] >= 100),
    ]
    for key, ok in conds:
        if ok:
            grant_badge(uid, key)


def count_badges(uid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT COUNT(*) AS n FROM user_badges WHERE user_id = %s", (uid,))
            r = c.fetchone()
    return r["n"] if r else 0


# ============================================================
# learning cards
# ============================================================
def create_card(uid, class_id, content):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO learning_cards (user_id, class_id, content, created_at) VALUES (%s, %s, %s, %s)",
                (uid, class_id, content, now()),
            )
        conn.commit()


def list_user_cards(uid, limit=20):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT lc.*, c.title AS class_title, c.subject AS class_subject
                FROM learning_cards lc JOIN classes c ON c.id = lc.class_id
                WHERE lc.user_id = %s ORDER BY lc.id DESC LIMIT %s""",
                (uid, limit),
            )
            return c.fetchall()


# ============================================================
# classes
# ============================================================
def create_class(title, subject, description, teacher_id, join_code,
                 is_public=1, taught_by="", is_weekly=0, weekly_time="", next_session=""):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            try:
                c.execute(
                    """INSERT INTO classes
                    (title, subject, description, teacher_id, join_code, is_public, created_at,
                     blackboard, stage, taught_by, is_weekly, weekly_time, next_session)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s)
                    RETURNING id""",
                    (title, subject, description, teacher_id, join_code, is_public, now(),
                     taught_by, is_weekly, weekly_time, next_session),
                )
                cid = c.fetchone()["id"]
                c.execute(
                    "INSERT INTO enrollments (class_id, user_id, role, joined_at) VALUES (%s, %s, 'teacher', %s)",
                    (cid, teacher_id, now()),
                )
                conn.commit()
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return None
    check_badges(teacher_id)
    return cid


def get_class_by_code(code):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM classes WHERE join_code = %s", (code,))
            return c.fetchone()


def get_class_by_id(cid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM classes WHERE id = %s", (cid,))
            return c.fetchone()


def list_public_classes(query="", subject=""):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            where = ["c.is_public IN (1, 2)"]
            params = []
            if query:
                like = f"%{query}%"
                where.append("(c.title ILIKE %s OR c.subject ILIKE %s OR c.description ILIKE %s)")
                params += [like, like, like]
            if subject:
                where.append("c.subject = %s")
                params.append(subject)
            sql = f"""SELECT c.*, u.name AS teacher_name FROM classes c
                JOIN users u ON u.id = c.teacher_id
                WHERE {' AND '.join(where)}
                ORDER BY c.is_weekly DESC, c.created_at DESC LIMIT 50"""
            c.execute(sql, params)
            return c.fetchall()


def list_subjects(limit=30):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT subject, COUNT(*) as n FROM classes
                WHERE is_public = 1 AND subject != ''
                GROUP BY subject ORDER BY n DESC LIMIT %s""",
                (limit,),
            )
            return c.fetchall()


def list_weekly_classes(limit=20):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT c.*, u.name AS teacher_name FROM classes c
                JOIN users u ON u.id = c.teacher_id
                WHERE c.is_weekly = 1 AND c.is_public = 1
                ORDER BY c.created_at DESC LIMIT %s""",
                (limit,),
            )
            return c.fetchall()


def list_classes_taught_by(uid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT * FROM classes WHERE teacher_id = %s ORDER BY created_at DESC",
                (uid,),
            )
            return c.fetchall()


def count_students(class_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT COUNT(*) AS n FROM enrollments WHERE class_id = %s AND role = 'student'",
                (class_id,),
            )
            r = c.fetchone()
    return r["n"] if r else 0


def join_class(class_id, user_id, role="student"):
    with get_conn() as conn:
        with conn.cursor() as c:
            try:
                c.execute(
                    "INSERT INTO enrollments (class_id, user_id, role, joined_at) VALUES (%s, %s, %s, %s)",
                    (class_id, user_id, role, now()),
                )
                conn.commit()
                ok = True
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                ok = False
    if ok:
        check_badges(user_id)
    return ok


def list_classes_for_user(user_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT c.*, e.role FROM classes c
                JOIN enrollments e ON e.class_id = c.id
                WHERE e.user_id = %s
                ORDER BY c.created_at DESC""",
                (user_id,),
            )
            return c.fetchall()


def list_members(class_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT u.id AS user_id, u.name, u.skin, e.role FROM enrollments e
                JOIN users u ON u.id = e.user_id
                WHERE e.class_id = %s
                ORDER BY e.joined_at""",
                (class_id,),
            )
            return c.fetchall()


def get_role(class_id, user_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT role FROM enrollments WHERE class_id = %s AND user_id = %s",
                (class_id, user_id),
            )
            r = c.fetchone()
    return r["role"] if r else None


def set_blackboard(class_id, text):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE classes SET blackboard = %s WHERE id = %s", (text, class_id))
        conn.commit()


def set_stage(class_id, stage):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE classes SET stage = %s WHERE id = %s", (stage, class_id))
        conn.commit()


# ============================================================
# messages
# ============================================================
def add_message(class_id, sender_type, sender_name, content):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """INSERT INTO messages (class_id, sender_type, sender_name, content, helpful_count, created_at)
                VALUES (%s, %s, %s, %s, 0, %s)""",
                (class_id, sender_type, sender_name, content, now()),
            )
        conn.commit()


def get_messages(class_id, limit=80):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT * FROM messages WHERE class_id = %s ORDER BY id ASC LIMIT %s",
                (class_id, limit),
            )
            return c.fetchall()


def mark_helpful(message_id, user_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            try:
                c.execute(
                    "INSERT INTO message_helpful (message_id, user_id, created_at) VALUES (%s, %s, %s)",
                    (message_id, user_id, now()),
                )
                c.execute(
                    "UPDATE messages SET helpful_count = helpful_count + 1 WHERE id = %s",
                    (message_id,),
                )
                conn.commit()
                c.execute(
                    "SELECT helpful_count, sender_name FROM messages WHERE id = %s",
                    (message_id,),
                )
                row = c.fetchone()
                sender = get_user_by_name(row["sender_name"])
                if sender:
                    check_badges(sender["id"])
                return True, row["helpful_count"]
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                c.execute("SELECT helpful_count FROM messages WHERE id = %s", (message_id,))
                row = c.fetchone()
                return False, (row["helpful_count"] if row else 0)


def get_message(message_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
            return c.fetchone()


# ============================================================
# steps
# ============================================================
def add_step(class_id, title, description=""):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT COALESCE(MAX(position), -1) AS m FROM class_steps WHERE class_id = %s",
                (class_id,),
            )
            r = c.fetchone()
            pos = (r["m"] if r else -1) + 1
            c.execute(
                """INSERT INTO class_steps (class_id, position, title, description, created_at)
                VALUES (%s, %s, %s, %s, %s)""",
                (class_id, pos, title, description or "", now()),
            )
        conn.commit()


def list_steps(class_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT * FROM class_steps WHERE class_id = %s ORDER BY position ASC, id ASC",
                (class_id,),
            )
            return c.fetchall()


def delete_step(step_id):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM class_steps WHERE id = %s", (step_id,))
        conn.commit()


# ============================================================
# join requests
# ============================================================
def create_join_request(class_id, user_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            try:
                c.execute(
                    "INSERT INTO join_requests (class_id, user_id, status, created_at) VALUES (%s, %s, 'pending', %s) RETURNING id",
                    (class_id, user_id, now()),
                )
                rid = c.fetchone()["id"]
                conn.commit()
                return rid
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                c.execute(
                    "UPDATE join_requests SET status='pending' WHERE class_id=%s AND user_id=%s",
                    (class_id, user_id),
                )
                conn.commit()
                return None


def list_pending_requests_for_teacher(teacher_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT r.*, u.name AS user_name, c.title AS class_title, c.id AS class_id
                FROM join_requests r
                JOIN users u ON u.id = r.user_id
                JOIN classes c ON c.id = r.class_id
                WHERE c.teacher_id = %s AND r.status = 'pending'
                ORDER BY r.created_at DESC""",
                (teacher_id,),
            )
            return c.fetchall()


def get_request_by_id(rid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM join_requests WHERE id = %s", (rid,))
            return c.fetchone()


def set_request_status(rid, status):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE join_requests SET status = %s WHERE id = %s", (status, rid))
        conn.commit()


def count_pending_for_teacher(teacher_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT COUNT(*) AS n FROM join_requests r
                JOIN classes c ON c.id = r.class_id
                WHERE c.teacher_id = %s AND r.status = 'pending'""",
                (teacher_id,),
            )
            r = c.fetchone()
    return r["n"] if r else 0


def list_my_requests(user_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT r.*, c.title AS class_title
                FROM join_requests r
                JOIN classes c ON c.id = r.class_id
                WHERE r.user_id = %s
                ORDER BY r.created_at DESC""",
                (user_id,),
            )
            return c.fetchall()


# ============================================================
# blackboard history
# ============================================================
def save_blackboard_history(class_id, content, author):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """INSERT INTO blackboard_history (class_id, content, author, created_at)
                VALUES (%s, %s, %s, %s)""",
                (class_id, content or "", author or "", now()),
            )
        conn.commit()


def list_blackboard_history(class_id, limit=50):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                "SELECT * FROM blackboard_history WHERE class_id = %s ORDER BY id DESC LIMIT %s",
                (class_id, limit),
            )
            return c.fetchall()


def get_blackboard_history_by_id(hid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM blackboard_history WHERE id = %s", (hid,))
            return c.fetchone()


# ============================================================
# bans
# ============================================================
def ban_user(class_id, user_id, reason=""):
    with get_conn() as conn:
        with conn.cursor() as c:
            try:
                c.execute(
                    "INSERT INTO class_bans (class_id, user_id, reason, created_at) VALUES (%s, %s, %s, %s)",
                    (class_id, user_id, reason or "", now()),
                )
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                c.execute(
                    "UPDATE class_bans SET reason = %s WHERE class_id = %s AND user_id = %s",
                    (reason or "", class_id, user_id),
                )
            c.execute("DELETE FROM enrollments WHERE class_id = %s AND user_id = %s", (class_id, user_id))
        conn.commit()


def unban_user(class_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM class_bans WHERE class_id = %s AND user_id = %s", (class_id, user_id))
        conn.commit()


def is_banned(class_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT 1 FROM class_bans WHERE class_id = %s AND user_id = %s",
                (class_id, user_id),
            )
            return bool(c.fetchone())


def list_bans(class_id):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT b.*, u.name AS user_name FROM class_bans b
                JOIN users u ON u.id = b.user_id
                WHERE b.class_id = %s ORDER BY b.created_at DESC""",
                (class_id,),
            )
            return c.fetchall()


def kick_user(class_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM enrollments WHERE class_id = %s AND user_id = %s", (class_id, user_id))
        conn.commit()


# ============================================================
# questions
# ============================================================
def create_question(class_id, content, is_anonymous, asked_by):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """INSERT INTO questions (class_id, content, is_anonymous, asked_by, created_at)
                VALUES (%s, %s, %s, %s, %s)""",
                (class_id, content, 1 if is_anonymous else 0, asked_by, now()),
            )
        conn.commit()


def list_questions(class_id, limit=100):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT q.*, u.name AS asker_name, t.name AS answerer_name
                FROM questions q
                LEFT JOIN users u ON u.id = q.asked_by
                LEFT JOIN users t ON t.id = q.answered_by
                WHERE q.class_id = %s
                ORDER BY (q.answer IS NULL) DESC, q.id DESC
                LIMIT %s""",
                (class_id, limit),
            )
            return c.fetchall()


def get_question(qid):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM questions WHERE id = %s", (qid,))
            return c.fetchone()


def answer_question(qid, answer, answered_by):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE questions SET answer = %s, answered_by = %s, answered_at = %s WHERE id = %s",
                (answer, answered_by, now(), qid),
            )
        conn.commit()
    check_badges(answered_by)


def delete_question(qid):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM questions WHERE id = %s", (qid,))
        conn.commit()


def list_questions_answered_by(uid, limit=20):
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute(
                """SELECT q.*, c.title AS class_title FROM questions q
                JOIN classes c ON c.id = q.class_id
                WHERE q.answered_by = %s
                ORDER BY q.answered_at DESC LIMIT %s""",
                (uid, limit),
            )
            return c.fetchall()


# ============================================================
# poll_data (for /api/poll)
# ============================================================
def poll_data(class_id, user_id, since_msg_id=0):
    """ポーリング用に必要なデータを1接続でまとめて取得。"""
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("""
                SELECT c.blackboard, c.stage,
                       EXISTS(SELECT 1 FROM enrollments WHERE class_id = c.id AND user_id = %s) AS is_member,
                       EXISTS(SELECT 1 FROM class_bans WHERE class_id = c.id AND user_id = %s) AS is_banned
                FROM classes c WHERE c.id = %s
            """, (user_id, user_id, class_id))
            cls = c.fetchone()
            if not cls:
                return None, "not_found"
            if cls["is_banned"]:
                return None, "banned"
            if not cls["is_member"]:
                return None, "not_member"

            c.execute("""
                SELECT id, sender_type AS type, sender_name AS name,
                       content, helpful_count AS helpful
                FROM messages
                WHERE class_id = %s AND id > %s
                ORDER BY id ASC LIMIT 100
            """, (class_id, since_msg_id))
            msgs = c.fetchall()

            c.execute("""
                SELECT q.id, q.content, q.answer, q.is_anonymous,
                       u.name AS asker, t.name AS answerer,
                       q.created_at, q.answered_at
                FROM questions q
                LEFT JOIN users u ON u.id = q.asked_by
                LEFT JOIN users t ON t.id = q.answered_by
                WHERE q.class_id = %s
                ORDER BY (q.answer IS NULL) DESC, q.id DESC LIMIT 100
            """, (class_id,))
            questions = c.fetchall()

    return {
        "blackboard": cls["blackboard"] or "",
        "stage": cls["stage"] or 0,
        "messages": [dict(m) for m in msgs],
        "questions": [dict(q) for q in questions],
    }, None

def get_class_bundle(class_id, user_id):
    """教室ページ用：1接続で必要なデータをまとめて取得。"""
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
            cls = c.fetchone()
            if not cls:
                return None
            c.execute(
                "SELECT role FROM enrollments WHERE class_id = %s AND user_id = %s",
                (class_id, user_id),
            )
            role_row = c.fetchone()
            role = role_row["role"] if role_row else None
            c.execute(
                "SELECT 1 FROM class_bans WHERE class_id = %s AND user_id = %s",
                (class_id, user_id),
            )
            is_banned = bool(c.fetchone())
            if is_banned or not role:
                return {"cls": cls, "role": role, "is_banned": is_banned, "is_member": bool(role),
                        "members": [], "messages": [], "steps": [], "questions": [], "bans": []}
            c.execute(
                """SELECT u.id AS user_id, u.name, u.skin, e.role FROM enrollments e
                JOIN users u ON u.id = e.user_id WHERE e.class_id = %s ORDER BY e.joined_at""",
                (class_id,),
            )
            members = c.fetchall()
            c.execute(
                "SELECT * FROM messages WHERE class_id = %s ORDER BY id ASC LIMIT 80",
                (class_id,),
            )
            messages = c.fetchall()
            c.execute(
                "SELECT * FROM class_steps WHERE class_id = %s ORDER BY position ASC, id ASC",
                (class_id,),
            )
            steps = c.fetchall()
            c.execute(
                """SELECT q.*, u.name AS asker_name, t.name AS answerer_name
                FROM questions q
                LEFT JOIN users u ON u.id = q.asked_by
                LEFT JOIN users t ON t.id = q.answered_by
                WHERE q.class_id = %s
                ORDER BY (q.answer IS NULL) DESC, q.id DESC LIMIT 100""",
                (class_id,),
            )
            questions = c.fetchall()
            if role == "teacher":
                c.execute(
                    """SELECT b.*, u.name AS user_name FROM class_bans b
                    JOIN users u ON u.id = b.user_id
                    WHERE b.class_id = %s ORDER BY b.created_at DESC""",
                    (class_id,),
                )
                bans = c.fetchall()
            else:
                bans = []
    return {
        "cls": cls, "role": role, "is_banned": is_banned, "is_member": True,
        "members": members, "messages": messages, "steps": steps,
        "questions": questions, "bans": bans,
    }