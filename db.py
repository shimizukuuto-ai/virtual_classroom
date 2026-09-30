import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "classroom.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return datetime.now().strftime("%Y-%m-%d")


# ============================================================
# バッジ定義
# ============================================================
BADGES = {
    # key: (name_ja, name_en, desc_ja, desc_en, icon_svg_id)
    "first_class":     ("初授業", "First Class", "最初のクラスを開いた", "Taught your first class", "star"),
    "class_10":        ("常連講師", "Regular", "10クラス開講", "Taught 10 classes", "book"),
    "class_50":        ("講師の鑑", "Master Teacher", "50クラス開講", "Taught 50 classes", "crown"),
    "first_answer":    ("初回答", "First Answer", "Q&Aに初回答", "Answered your first question", "chat"),
    "answer_20":       ("賢者", "Wise One", "Q&Aに20回答", "Answered 20 questions", "brain"),
    "helpful_10":      ("役立つ人", "Helpful", "役に立った10回", "10 helpful votes", "thumb"),
    "helpful_100":     ("頼れる存在", "Trusted", "役に立った100回", "100 helpful votes", "shield"),
    "streak_3":        ("三日坊主返上", "3-Day Streak", "3日連続参加", "3-day streak", "fire1"),
    "streak_7":        ("一週間の習慣", "7-Day Streak", "7日連続参加", "7-day streak", "fire2"),
    "streak_30":       ("皆勤賞", "Perfect Month", "30日連続参加", "30-day streak", "fire3"),
    "first_weekly":    ("週次デビュー", "Weekly Debut", "初の週次公開授業", "Hosted first weekly class", "calendar"),
    "weekly_10":       ("週次マスター", "Weekly Master", "週次公開授業10回", "Hosted 10 weekly classes", "trophy"),
    "students_10":     ("10人の先生", "10 Students", "累計10人の生徒", "Taught 10 students total", "users"),
    "students_100":    ("100人の先生", "100 Students", "累計100人の生徒", "Taught 100 students total", "globe"),
}

# ============================================================
# スキン定義（XPで解放）
# ============================================================
SKINS = {
    # key: (name_ja, name_en, xp_required, color_hex)
    "default":  ("標準", "Default", 0, "0x3b82f6"),
    "glasses":  ("眼鏡", "Glasses", 100, "0x6366f1"),
    "hat":      ("帽子", "Hat", 300, "0xf59e0b"),
    "robe":     ("ローブ", "Robe", 800, "0x8b5cf6"),
    "crown":    ("王冠", "Crown", 2000, "0xfbbf24"),
    "aura":     ("オーラ", "Aura", 5000, "0xef4444"),
}

# ============================================================
# ランク定義
# ============================================================
RANKS = [
    # (key, min_xp, name_ja, name_en, color)
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
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        lang TEXT NOT NULL DEFAULT 'ja',
        title TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        skin TEXT DEFAULT 'default',
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
        blackboard TEXT DEFAULT '',
        stage INTEGER DEFAULT 0,
        taught_by TEXT DEFAULT '',
        is_weekly INTEGER DEFAULT 0,
        weekly_time TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS class_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
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
        helpful_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS message_helpful (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(message_id, user_id)
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
    CREATE TABLE IF NOT EXISTS class_bans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(class_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        is_anonymous INTEGER DEFAULT 1,
        asked_by INTEGER,
        answered_by INTEGER,
        answer TEXT,
        answered_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        badge_key TEXT NOT NULL,
        earned_at TEXT NOT NULL,
        UNIQUE(user_id, badge_key)
    );
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        UNIQUE(user_id, class_id, date)
    );
    CREATE TABLE IF NOT EXISTS learning_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    for ddl in [
        "ALTER TABLE users ADD COLUMN title TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN skin TEXT DEFAULT 'default'",
        "ALTER TABLE messages ADD COLUMN helpful_count INTEGER DEFAULT 0",
        "ALTER TABLE classes ADD COLUMN is_weekly INTEGER DEFAULT 0",
        "ALTER TABLE classes ADD COLUMN weekly_time TEXT DEFAULT ''",
                "ALTER TABLE classes ADD COLUMN next_session TEXT DEFAULT ''",
    ]:
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


# ============================================================
# users
# ============================================================
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


def update_user_profile(uid, title, bio):
    conn = get_conn()
    conn.execute("UPDATE users SET title = ?, bio = ? WHERE id = ?", (title or "", bio or "", uid))
    conn.commit()
    conn.close()


def set_user_skin(uid, skin_key):
    if skin_key not in SKINS:
        return False
    xp = calc_xp(uid)
    req = SKINS[skin_key][2]
    if xp < req:
        return False
    conn = get_conn()
    conn.execute("UPDATE users SET skin = ? WHERE id = ?", (skin_key, uid))
    conn.commit()
    conn.close()
    return True


def list_all_users(limit=200):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def delete_user(uid):
    conn = get_conn()
    for t in ("enrollments", "join_requests", "class_bans", "user_badges",
              "attendance", "learning_cards"):
        conn.execute(f"DELETE FROM {t} WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()


# ============================================================
# stats / XP / rank
# ============================================================
def user_stats(uid):
    user = get_user_by_id(uid)
    if not user:
        return None
    conn = get_conn()
    name = user["name"]
    helpful = conn.execute(
        "SELECT COALESCE(SUM(helpful_count),0) AS n FROM messages WHERE sender_name = ? AND sender_type = 'user'",
        (name,),
    ).fetchone()["n"]
    msg_count = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE sender_name = ? AND sender_type = 'user'",
        (name,),
    ).fetchone()["n"]
    taught = conn.execute(
        "SELECT COUNT(*) AS n FROM classes WHERE teacher_id = ?", (uid,)
    ).fetchone()["n"]
    weekly_hosted = conn.execute(
        "SELECT COUNT(*) AS n FROM classes WHERE teacher_id = ? AND is_weekly = 1", (uid,)
    ).fetchone()["n"]
    joined = conn.execute(
        "SELECT COUNT(*) AS n FROM enrollments WHERE user_id = ? AND role = 'student'",
        (uid,),
    ).fetchone()["n"]
    answers = conn.execute(
        "SELECT COUNT(*) AS n FROM questions WHERE answered_by = ?", (uid,)
    ).fetchone()["n"]
    students_total = conn.execute(
        """SELECT COUNT(*) AS n FROM enrollments e
        JOIN classes c ON c.id = e.class_id
        WHERE c.teacher_id = ? AND e.role = 'student'""",
        (uid,),
    ).fetchone()["n"]
    conn.close()
    xp = helpful * 5 + answers * 20 + taught * 50 + weekly_hosted * 30 + students_total * 2
    rank = rank_for_xp(xp)
    nxt = next_rank(xp)
    return {
        "helpful": helpful, "messages": msg_count, "taught": taught,
        "joined": joined, "answers": answers, "weekly_hosted": weekly_hosted,
        "students_total": students_total,
        "xp": xp,
        "rank": rank, "next_rank": nxt,
    }


def calc_xp(uid):
    s = user_stats(uid)
    return s["xp"] if s else 0


def calc_streak(uid):
    """連続参加日数を計算。attendance テーブルから。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT date FROM attendance WHERE user_id = ? ORDER BY date DESC LIMIT 60",
        (uid,),
    ).fetchall()
    conn.close()
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
    """クラス入室時に呼ぶ。連続記録が更新される。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO attendance (user_id, class_id, date) VALUES (?, ?, ?)",
            (uid, class_id, today()),
        )
        conn.commit()
        newly = True
    except sqlite3.IntegrityError:
        newly = False
    conn.close()
    if newly:
        check_badges(uid)
    return newly


# ============================================================
# badges
# ============================================================
def list_user_badges(uid):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM user_badges WHERE user_id = ? ORDER BY earned_at DESC",
        (uid,),
    ).fetchall()
    conn.close()
    return rows


def has_badge(uid, key):
    conn = get_conn()
    r = conn.execute(
        "SELECT 1 FROM user_badges WHERE user_id = ? AND badge_key = ?",
        (uid, key),
    ).fetchone()
    conn.close()
    return bool(r)


def grant_badge(uid, key):
    if key not in BADGES:
        return False
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO user_badges (user_id, badge_key, earned_at) VALUES (?, ?, ?)",
            (uid, key, now()),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def check_badges(uid):
    """進捗に応じて自動でバッジを付与する。"""
    s = user_stats(uid)
    if not s:
        return
    streak = calc_streak(uid)
    conds = [
        ("first_class",  s["taught"] >= 1),
        ("class_10",     s["taught"] >= 10),
        ("class_50",     s["taught"] >= 50),
        ("first_answer", s["answers"] >= 1),
        ("answer_20",    s["answers"] >= 20),
        ("helpful_10",   s["helpful"] >= 10),
        ("helpful_100",  s["helpful"] >= 100),
        ("streak_3",     streak >= 3),
        ("streak_7",     streak >= 7),
        ("streak_30",    streak >= 30),
        ("first_weekly", s["weekly_hosted"] >= 1),
        ("weekly_10",    s["weekly_hosted"] >= 10),
        ("students_10",  s["students_total"] >= 10),
        ("students_100", s["students_total"] >= 100),
    ]
    for key, ok in conds:
        if ok:
            grant_badge(uid, key)


def count_badges(uid):
    conn = get_conn()
    r = conn.execute(
        "SELECT COUNT(*) AS n FROM user_badges WHERE user_id = ?", (uid,)
    ).fetchone()
    conn.close()
    return r["n"] if r else 0


# ============================================================
# learning cards
# ============================================================
def create_card(uid, class_id, content):
    conn = get_conn()
    conn.execute(
        "INSERT INTO learning_cards (user_id, class_id, content, created_at) VALUES (?, ?, ?, ?)",
        (uid, class_id, content, now()),
    )
    conn.commit()
    conn.close()


def list_user_cards(uid, limit=20):
    conn = get_conn()
    rows = conn.execute(
        """SELECT lc.*, c.title AS class_title, c.subject AS class_subject
        FROM learning_cards lc JOIN classes c ON c.id = lc.class_id
        WHERE lc.user_id = ? ORDER BY lc.id DESC LIMIT ?""",
        (uid, limit),
    ).fetchall()
    conn.close()
    return rows


# ============================================================
# classes
# ============================================================
def create_class(title, subject, description, teacher_id, join_code,
                 is_public=1, taught_by="", is_weekly=0, weekly_time="", next_session=""):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO classes
            (title, subject, description, teacher_id, join_code, is_public, created_at,
             blackboard, stage, taught_by, is_weekly, weekly_time, next_session)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', 0, ?, ?, ?, ?)""",
            (title, subject, description, teacher_id, join_code, is_public, now(),
             taught_by, is_weekly, weekly_time, next_session),
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
    check_badges(teacher_id)
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


def list_public_classes(query="", subject=""):
    conn = get_conn()
    where = ["c.is_public = 1"]
    params = []
    if query:
        like = f"%{query}%"
        where.append("(c.title LIKE ? OR c.subject LIKE ? OR c.description LIKE ?)")
        params += [like, like, like]
    if subject:
        where.append("c.subject = ?")
        params.append(subject)
    sql = f"""SELECT c.*, u.name AS teacher_name FROM classes c
        JOIN users u ON u.id = c.teacher_id
        WHERE {' AND '.join(where)}
        ORDER BY c.is_weekly DESC, c.created_at DESC LIMIT 50"""
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def list_weekly_classes(limit=20):
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.*, u.name AS teacher_name FROM classes c
        JOIN users u ON u.id = c.teacher_id
        WHERE c.is_weekly = 1 AND c.is_public = 1
        ORDER BY c.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def list_classes_taught_by(uid):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM classes WHERE teacher_id = ? ORDER BY created_at DESC",
        (uid,),
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
    check_badges(user_id)
    return True


def list_classes_for_user(user_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.*, e.role FROM classes c
        JOIN enrollments e ON e.class_id = c.id
        WHERE e.user_id = ?
        ORDER BY c.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def list_members(class_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT u.id AS user_id, u.name, u.skin, e.role FROM enrollments e
        JOIN users u ON u.id = e.user_id
        WHERE e.class_id = ?
        ORDER BY e.joined_at""",
        (class_id,),
    ).fetchall()
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


def set_stage(class_id, stage):
    conn = get_conn()
    conn.execute("UPDATE classes SET stage = ? WHERE id = ?", (stage, class_id))
    conn.commit()
    conn.close()


# ============================================================
# messages
# ============================================================
def add_message(class_id, sender_type, sender_name, content):
    conn = get_conn()
    conn.execute(
        """INSERT INTO messages (class_id, sender_type, sender_name, content, helpful_count, created_at)
        VALUES (?, ?, ?, ?, 0, ?)""",
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


def mark_helpful(message_id, user_id):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO message_helpful (message_id, user_id, created_at) VALUES (?, ?, ?)",
            (message_id, user_id, now()),
        )
        conn.execute(
            "UPDATE messages SET helpful_count = helpful_count + 1 WHERE id = ?",
            (message_id,),
        )
        conn.commit()
        count = conn.execute(
            "SELECT helpful_count FROM messages WHERE id = ?", (message_id,)
        ).fetchone()["helpful_count"]
        # メッセージの送信者にバッジチェック
        m = conn.execute("SELECT sender_name FROM messages WHERE id = ?", (message_id,)).fetchone()
        conn.close()
        if m:
            sender = get_user_by_name(m["sender_name"])
            if sender:
                check_badges(sender["id"])
        return True, count
    except sqlite3.IntegrityError:
        count = conn.execute(
            "SELECT helpful_count FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        conn.close()
        return False, (count["helpful_count"] if count else 0)


def get_message(message_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    conn.close()
    return r


# ============================================================
# steps
# ============================================================
def add_step(class_id, title, description=""):
    conn = get_conn()
    r = conn.execute(
        "SELECT COALESCE(MAX(position), -1) AS m FROM class_steps WHERE class_id = ?",
        (class_id,),
    ).fetchone()
    pos = (r["m"] if r else -1) + 1
    conn.execute(
        """INSERT INTO class_steps (class_id, position, title, description, created_at)
        VALUES (?, ?, ?, ?, ?)""",
        (class_id, pos, title, description or "", now()),
    )
    conn.commit()
    conn.close()


def list_steps(class_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM class_steps WHERE class_id = ? ORDER BY position ASC, id ASC",
        (class_id,),
    ).fetchall()
    conn.close()
    return rows


def delete_step(step_id):
    conn = get_conn()
    conn.execute("DELETE FROM class_steps WHERE id = ?", (step_id,))
    conn.commit()
    conn.close()


# ============================================================
# join requests
# ============================================================
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
    rows = conn.execute(
        """SELECT r.*, u.name AS user_name, c.title AS class_title, c.id AS class_id
        FROM join_requests r
        JOIN users u ON u.id = r.user_id
        JOIN classes c ON c.id = r.class_id
        WHERE c.teacher_id = ? AND r.status = 'pending'
        ORDER BY r.created_at DESC""",
        (teacher_id,),
    ).fetchall()
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
    r = conn.execute(
        """SELECT COUNT(*) AS n FROM join_requests r
        JOIN classes c ON c.id = r.class_id
        WHERE c.teacher_id = ? AND r.status = 'pending'""",
        (teacher_id,),
    ).fetchone()
    conn.close()
    return r["n"] if r else 0


def list_my_requests(user_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT r.*, c.title AS class_title
        FROM join_requests r
        JOIN classes c ON c.id = r.class_id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


# ============================================================
# blackboard history
# ============================================================
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
        "SELECT * FROM blackboard_history WHERE class_id = ? ORDER BY id DESC LIMIT ?",
        (class_id, limit),
    ).fetchall()
    conn.close()
    return rows


def get_blackboard_history_by_id(hid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM blackboard_history WHERE id = ?", (hid,)).fetchone()
    conn.close()
    return r


# ============================================================
# bans
# ============================================================
def ban_user(class_id, user_id, reason=""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO class_bans (class_id, user_id, reason, created_at) VALUES (?, ?, ?, ?)",
            (class_id, user_id, reason or "", now()),
        )
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE class_bans SET reason = ? WHERE class_id = ? AND user_id = ?",
            (reason or "", class_id, user_id),
        )
    conn.execute("DELETE FROM enrollments WHERE class_id = ? AND user_id = ?", (class_id, user_id))
    conn.commit()
    conn.close()


def unban_user(class_id, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM class_bans WHERE class_id = ? AND user_id = ?", (class_id, user_id))
    conn.commit()
    conn.close()


def is_banned(class_id, user_id):
    conn = get_conn()
    r = conn.execute(
        "SELECT 1 FROM class_bans WHERE class_id = ? AND user_id = ?",
        (class_id, user_id),
    ).fetchone()
    conn.close()
    return bool(r)


def list_bans(class_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT b.*, u.name AS user_name FROM class_bans b
        JOIN users u ON u.id = b.user_id
        WHERE b.class_id = ? ORDER BY b.created_at DESC""",
        (class_id,),
    ).fetchall()
    conn.close()
    return rows


def kick_user(class_id, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM enrollments WHERE class_id = ? AND user_id = ?", (class_id, user_id))
    conn.commit()
    conn.close()


# ============================================================
# questions
# ============================================================
def create_question(class_id, content, is_anonymous, asked_by):
    conn = get_conn()
    conn.execute(
        """INSERT INTO questions (class_id, content, is_anonymous, asked_by, created_at)
        VALUES (?, ?, ?, ?, ?)""",
        (class_id, content, 1 if is_anonymous else 0, asked_by, now()),
    )
    conn.commit()
    conn.close()


def list_questions(class_id, limit=100):
    conn = get_conn()
    rows = conn.execute(
        """SELECT q.*, u.name AS asker_name, t.name AS answerer_name
        FROM questions q
        LEFT JOIN users u ON u.id = q.asked_by
        LEFT JOIN users t ON t.id = q.answered_by
        WHERE q.class_id = ?
        ORDER BY (q.answer IS NULL) DESC, q.id DESC
        LIMIT ?""",
        (class_id, limit),
    ).fetchall()
    conn.close()
    return rows


def get_question(qid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    conn.close()
    return r


def answer_question(qid, answer, answered_by):
    conn = get_conn()
    conn.execute(
        "UPDATE questions SET answer = ?, answered_by = ?, answered_at = ? WHERE id = ?",
        (answer, answered_by, now(), qid),
    )
    conn.commit()
    conn.close()
    check_badges(answered_by)


def delete_question(qid):
    conn = get_conn()
    conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
    conn.commit()
    conn.close()


def list_questions_answered_by(uid, limit=20):
    conn = get_conn()
    rows = conn.execute(
        """SELECT q.*, c.title AS class_title FROM questions q
        JOIN classes c ON c.id = q.class_id
        WHERE q.answered_by = ?
        ORDER BY q.answered_at DESC LIMIT ?""",
        (uid, limit),
    ).fetchall()
    conn.close()
    return rows

def list_subjects(limit=30):
    conn = get_conn()
    rows = conn.execute(
        """SELECT subject, COUNT(*) as n FROM classes
        WHERE is_public = 1 AND subject != ''
        GROUP BY subject ORDER BY n DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return rows