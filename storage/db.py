import sqlite3
import hashlib
import json
import re
from werkzeug.security import generate_password_hash, check_password_hash
import difflib


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def normalize_plain(text: str) -> str:
    """
    Normalizează textul pentru:
    - căutare în DB (LIKE)
    - hash stabil (deduplicare)
    Păstrează conținutul (inclusiv LaTeX), doar curăță whitespace.
    """
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)      # spații multiple
    t = re.sub(r"\n{3,}", "\n\n", t)   # prea multe linii goale
    return t.strip()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS problems(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        level TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        source TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    """)
    conn.commit()

    # Migrare: adaugă coloana hash dacă lipsește
    if not _has_column(conn, "problems", "hash"):
        conn.execute("ALTER TABLE problems ADD COLUMN hash TEXT")
        conn.commit()

    if not _has_column(conn, "problems", "pred_level"):
        conn.execute("ALTER TABLE problems ADD COLUMN pred_level TEXT")
        conn.commit()

    if not _has_column(conn, "problems", "pred_difficulty"):
        conn.execute("ALTER TABLE problems ADD COLUMN pred_difficulty TEXT")
        conn.commit()

    if not _has_column(conn, "problems", "pred_confidence"):
        conn.execute("ALTER TABLE problems ADD COLUMN pred_confidence REAL")
        conn.commit()

    # Migrare: raw/plain pentru LaTeX + căutare
    if not _has_column(conn, "problems", "text_raw"):
        conn.execute("ALTER TABLE problems ADD COLUMN text_raw TEXT")
        conn.commit()

    if not _has_column(conn, "problems", "text_plain"):
        conn.execute("ALTER TABLE problems ADD COLUMN text_plain TEXT")
        conn.commit()

    # Backfill pentru datele vechi (copiem din text unde lipsesc)
    conn.execute("""
        UPDATE problems
        SET text_raw = COALESCE(NULLIF(text_raw,''), text),
            text_plain = COALESCE(NULLIF(text_plain,''), text)
        WHERE text_raw IS NULL OR text_raw='' OR text_plain IS NULL OR text_plain=''
    """)
    conn.commit()

    # Index unic pe hash (previne dublurile)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_problems_hash_unique ON problems(hash)")
    conn.commit()

    # users
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        pass_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'teacher',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    """)
    conn.commit()

    # events (istoric)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        meta_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
      )
    """)
    conn.commit()

    # favorites per user
    conn.execute("""
      CREATE TABLE IF NOT EXISTS favorites(
        user_id INTEGER NOT NULL,
        problem_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, problem_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(problem_id) REFERENCES problems(id)
      )
    """)
    conn.commit()
    # saved filters per user
    conn.execute("""
      CREATE TABLE IF NOT EXISTS saved_filters(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        q TEXT DEFAULT '',
        subject TEXT DEFAULT '',
        level TEXT DEFAULT '',
        fav_only INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
      )
    """)
    conn.commit()

def compute_hash(subject: str, level: str, difficulty: str, text_plain: str) -> str:
    # normalizează minim: whitespace + lower (hash stabil)
    norm = normalize_plain(text_plain).lower()
    key = f"{subject.strip().lower()}|{level.strip().lower()}|{difficulty.strip().lower()}|{norm}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def insert_problem(conn: sqlite3.Connection, subject: str, level: str, difficulty: str,
                   source: str, text: str,
                   pred_level=None, pred_difficulty=None, pred_confidence=None):
    """
    text primit din UI/API este considerat text_raw.
    În DB păstrăm:
      - text_raw: original (poate include LaTeX)
      - text_plain: normalizat (whitespace) pentru căutare/hash
      - text: păstrăm compatibilitatea și setăm = text_plain (căutările existente merg)
    """
    if text is None:
        text_raw = ""
    elif isinstance(text, str):
        text_raw = text.strip()
    else:
        text_raw = str(text).strip()
    text_plain = normalize_plain(text_raw)

    h = compute_hash(subject, level, difficulty, text_plain)

    cur = conn.execute("""
      INSERT OR IGNORE INTO problems(
        subject,level,difficulty,source,
        text,hash,
        pred_level,pred_difficulty,pred_confidence,
        text_raw,text_plain
      )
      VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        subject, level, difficulty, source,
        text_plain, h,
        pred_level, pred_difficulty, pred_confidence,
        text_raw, text_plain
    ))
    conn.commit()

    if cur.rowcount == 1:
        return int(cur.lastrowid), False

    row = conn.execute("SELECT id FROM problems WHERE hash = ?", (h,)).fetchone()
    return int(row["id"]), True


def delete_problem(conn: sqlite3.Connection, problem_id: int) -> bool:
    conn.execute("DELETE FROM favorites WHERE problem_id = ?", (problem_id,))
    cur = conn.execute("DELETE FROM problems WHERE id = ?", (problem_id,))
    conn.commit()
    return cur.rowcount == 1


def search_problems(conn, user_id: int, q: str = "", subject: str = "", level: str = "", fav_only: bool = False):
    sql = """
      SELECT p.*,
             COALESCE(NULLIF(p.text_raw,''), p.text) AS text_display,
             CASE WHEN f.problem_id IS NULL THEN 0 ELSE 1 END AS is_fav
      FROM problems p
      LEFT JOIN favorites f
        ON f.problem_id = p.id AND f.user_id = ?
      WHERE 1=1
    """
    params = [user_id]

    if q.strip():
        # căutare pe textul compatibil (text = text_plain)
        sql += " AND p.text LIKE ?"
        params.append(f"%{q.strip()}%")
    if subject.strip():
        sql += " AND p.subject = ?"
        params.append(subject.strip())
    if level.strip():
        sql += " AND p.level = ?"
        params.append(level.strip())
    if fav_only:
        sql += " AND f.problem_id IS NOT NULL"

    sql += " ORDER BY p.id DESC"
    return conn.execute(sql, params).fetchall()


def list_distinct(conn: sqlite3.Connection, col: str):
    rows = conn.execute(f"SELECT DISTINCT {col} AS v FROM problems ORDER BY v ASC").fetchall()
    return [r["v"] for r in rows if r["v"]]


def ensure_default_admin(conn: sqlite3.Connection):
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    if int(row["n"]) == 0:
        conn.execute(
            "INSERT INTO users(email, pass_hash, role) VALUES (?,?,?)",
            ("admin@local", generate_password_hash("admin123"), "admin")
        )
        conn.commit()


def get_user_by_email(conn, email: str):
    return conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()


def get_user_by_id(conn, uid: int):
    return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def verify_login(conn, email: str, password: str):
    u = get_user_by_email(conn, email.strip().lower())
    if not u:
        return None
    if check_password_hash(u["pass_hash"], password):
        return u
    return None


def log_event(conn, user_id: int, action: str, meta: dict | None = None):
    conn.execute(
        "INSERT INTO events(user_id, action, meta_json) VALUES (?,?,?)",
        (user_id, action, json.dumps(meta or {}, ensure_ascii=False))
    )
    conn.commit()


def is_favorite(conn, user_id: int, problem_id: int) -> bool:
    r = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND problem_id=?",
        (user_id, problem_id)
    ).fetchone()
    return r is not None


def toggle_favorite(conn, user_id: int, problem_id: int) -> bool:
    if is_favorite(conn, user_id, problem_id):
        conn.execute("DELETE FROM favorites WHERE user_id=? AND problem_id=?",
                     (user_id, problem_id))
        conn.commit()
        return False
    conn.execute("INSERT INTO favorites(user_id, problem_id) VALUES (?,?)",
                 (user_id, problem_id))
    conn.commit()
    return True


def stats_actions(conn):
    return conn.execute("""
      SELECT u.email, u.role, e.action, COUNT(*) AS cnt
      FROM events e
      JOIN users u ON u.id = e.user_id
      GROUP BY u.email, u.role, e.action
      ORDER BY u.email, e.action
    """).fetchall()


def stats_actions_for_user(conn, user_id: int):
    return conn.execute("""
      SELECT action, COUNT(*) AS cnt
      FROM events
      WHERE user_id=?
      GROUP BY action
      ORDER BY action
    """, (user_id,)).fetchall()


def create_user(conn: sqlite3.Connection, email: str, password: str, role: str = "teacher"):
    email = (email or "").strip().lower()
    role = (role or "teacher").strip().lower()

    if not email or not password:
        return False, "Email/parolă lipsă"
    if role not in ("teacher", "admin"):
        return False, "Rol invalid"

    try:
        conn.execute(
            "INSERT INTO users(email, pass_hash, role) VALUES (?,?,?)",
            (email, generate_password_hash(password), role)
        )
        conn.commit()
        return True, "Creat"
    except sqlite3.IntegrityError:
        return False, "Email deja există"


def list_users(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT id, email, role, created_at FROM users ORDER BY id DESC"
    ).fetchall()


def delete_user(conn: sqlite3.Connection, user_id: int) -> bool:
    conn.execute("DELETE FROM events WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM favorites WHERE user_id=?", (user_id,))
    cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    return cur.rowcount == 1
def list_saved_filters(conn: sqlite3.Connection, user_id: int):
    return conn.execute("""
        SELECT id, user_id, name, q, subject, level, fav_only, created_at
        FROM saved_filters
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()


def insert_saved_filter(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    q: str = "",
    subject: str = "",
    level: str = "",
    fav_only: bool = False
):
    cur = conn.execute("""
        INSERT INTO saved_filters(user_id, name, q, subject, level, fav_only)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        (name or "").strip(),
        (q or "").strip(),
        (subject or "").strip(),
        (level or "").strip(),
        1 if fav_only else 0
    ))
    conn.commit()
    return int(cur.lastrowid)


def delete_saved_filter(conn: sqlite3.Connection, filter_id: int, user_id: int) -> bool:
    cur = conn.execute("""
        DELETE FROM saved_filters
        WHERE id = ? AND user_id = ?
    """, (filter_id, user_id))
    conn.commit()
    return cur.rowcount == 1
def count_problems(conn):
    row = conn.execute("SELECT COUNT(*) AS n FROM problems").fetchone()
    return int(row["n"] or 0)

def count_users(conn):
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(row["n"] or 0)

def count_favorites(conn):
    row = conn.execute("SELECT COUNT(*) AS n FROM favorites").fetchone()
    return int(row["n"] or 0)

def count_events_by_action(conn, action: str):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE action = ?",
        (action,)
    ).fetchone()
    return int(row["n"] or 0)
def text_similarity(a: str, b: str) -> float:
    a = normalize_plain(a or "").lower()
    b = normalize_plain(b or "").lower()
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_near_duplicate(conn, subject: str, level: str, difficulty: str, text: str, threshold: float = 0.90):
    text_plain = normalize_plain(text or "")

    rows = conn.execute("""
        SELECT id, subject, level, difficulty,
               COALESCE(NULLIF(text_raw,''), text) AS text_display
        FROM problems
        WHERE subject = ? AND level = ? AND difficulty = ?
    """, (subject, level, difficulty)).fetchall()

    best_row = None
    best_score = 0.0

    for r in rows:
        score = text_similarity(text_plain, r["text_display"])
        if score > best_score:
            best_score = score
            best_row = r

    if best_row and best_score >= threshold:
        return {
            "id": int(best_row["id"]),
            "text": best_row["text_display"],
            "score": round(best_score, 3)
        }

    return None