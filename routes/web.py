import random
from flask import (
    Blueprint, render_template, request, redirect, url_for, send_file,
    current_app, jsonify, session, g
)
from storage import db as dbmod
from services.ai_clients import generate_multi, generate_similar_multi
from services.pdf_export_premium import (
    export_bank_pdf_premium,
    export_selected_only_text_pdf_premium,
    export_smart_test_pdf_premium
)
from services.classifier import classify_problem

bp = Blueprint("web", __name__)

# ---------------- AUTH HELPERS ----------------

@bp.before_app_request
def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid:
        conn = current_app.config["DB_CONN"]
        g.user = dbmod.get_user_by_id(conn, int(uid))

def login_required(fn):
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("web.login"))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

def role_required(role: str):
    def deco(fn):
        def wrapper(*args, **kwargs):
            if not g.user:
                return redirect(url_for("web.login"))
            if g.user["role"] != role:
                return "Forbidden", 403
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco

# ---------------- LOGIN / LOGOUT ----------------

@bp.get("/login")
def login():
    return render_template("login.html", error=None)

@bp.post("/login")
def login_post():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    conn = current_app.config["DB_CONN"]
    u = dbmod.verify_login(conn, email, password)
    if not u:
        return render_template("login.html", error="Email/parolă greșite.")
    session["user_id"] = int(u["id"])
    dbmod.log_event(conn, int(u["id"]), "login", {})
    return redirect(url_for("web.index"))

@bp.get("/logout")
@login_required
def logout():
    conn = current_app.config["DB_CONN"]
    dbmod.log_event(conn, int(g.user["id"]), "logout", {})
    session.clear()
    return redirect(url_for("web.login"))

# ---------------- GENERARE (HOME) ----------------

@bp.get("/")
@login_required
def index():
    return render_template("index.html", items=None)

@bp.post("/generate")
@login_required
def generate():
    subject = request.form["subject"]
    level = request.form["level"]
    difficulty = request.form["difficulty"]
    n = int(request.form["n"])
    topic = request.form.get("topic", "").strip()

    cfg = current_app.config
    dbmod.log_event(cfg["DB_CONN"], int(g.user["id"]), "generate", {
        "subject": subject, "level": level, "difficulty": difficulty, "n": n, "topic": topic
    })
    
    items = generate_multi(
        cfg["GEMINI_API_KEY"], cfg["GEMINI_MODEL"],
        cfg["HF_TOKEN"], cfg["HF_MODEL"],
        subject, level, difficulty, n, topic
    )
    return render_template("index.html", items=items, subject=subject, level=level, difficulty=difficulty, topic=topic)

# ---------------- BANCA DE PROBLEME ----------------

def build_filter_name(q: str = "", subject: str = "", level: str = "", fav_only: bool = False) -> str:
    parts = []
    if subject.strip(): parts.append(subject.strip())
    if level.strip(): parts.append(level.strip())
    if q.strip(): parts.append(f'căutare: "{q.strip()}"')
    if fav_only: parts.append("favorite")
    return " • ".join(parts) if parts else "Filtru nou"

@bp.get("/bank")
@login_required
def bank():
    q = request.args.get("q", "")
    subject = request.args.get("subject", "")
    level = request.args.get("level", "")
    fav_only = (request.args.get("fav", "") == "1")

    conn = current_app.config["DB_CONN"]
    rows = dbmod.search_problems(conn, int(g.user["id"]), q=q, subject=subject, level=level, fav_only=fav_only)
    subjects = dbmod.list_distinct(conn, "subject")
    levels = dbmod.list_distinct(conn, "level")
    saved_filters = dbmod.list_saved_filters(conn, int(g.user["id"]))
    suggested_filter_name = build_filter_name(q, subject, level, fav_only)

    return render_template("bank.html", rows=rows, q=q, subject=subject, level=level, 
                           subjects=subjects, levels=levels, fav=fav_only, 
                           saved_filters=saved_filters, suggested_filter_name=suggested_filter_name)

@bp.post("/filters/save")
@login_required
def save_filter():
    name = request.form.get("filter_name", "").strip()
    q = request.form.get("q", "").strip()
    subject = request.form.get("subject", "").strip()
    level = request.form.get("level", "").strip()
    fav_only = (request.form.get("fav", "") == "1")
    conn = current_app.config["DB_CONN"]
    dbmod.insert_saved_filter(conn, int(g.user["id"]), name or build_filter_name(q, subject, level, fav_only), q, subject, level, fav_only)
    return redirect(url_for("web.bank", q=q, subject=subject, level=level, fav="1" if fav_only else ""))

# ---------------- EXPORTS ----------------

@bp.get("/export.pdf")
@login_required
def export_pdf():
    conn = current_app.config["DB_CONN"]
    db_rows = conn.execute("SELECT subject, level, difficulty, source, COALESCE(NULLIF(text_raw,''), text) AS text_raw FROM problems").fetchall()
    rows = [{"subject": r["subject"], "level": r["level"], "difficulty": r["difficulty"], "source": r["source"], "text": r["text_raw"]} for r in db_rows]
    path = export_bank_pdf_premium(rows, "banca_probleme.pdf")
    resp = send_file(path, as_attachment=True)
    resp.set_cookie("fileDownload", "true", max_age=10)
    return resp

@bp.post("/export_selected.pdf")
@login_required
def export_selected_pdf():
    ids = [int(x) for x in request.form.getlist("ids")]
    if not ids: return redirect(url_for("web.bank"))
    conn = current_app.config["DB_CONN"]
    placeholders = ",".join(["?"] * len(ids))
    db_rows = conn.execute(f"SELECT COALESCE(NULLIF(text_raw,''), text) AS text_raw FROM problems WHERE id IN ({placeholders})", ids).fetchall()
    rows = [{"text": r["text_raw"]} for r in db_rows]
    path = export_selected_only_text_pdf_premium(rows, "test_selectie.pdf")
    resp = send_file(path, as_attachment=True)
    resp.set_cookie("fileDownload", "true", max_age=10)
    return resp

@bp.post("/export_smart_test")
@login_required
def export_smart_test():
    subject = request.form.get("subject", "").strip()
    level = request.form.get("level", "").strip()
    q = request.form.get("q", "").strip()
    difficulty = request.form.get("difficulty", "medie")
    num_tests = int(request.form.get("num_tests", 1))
    problems_per_test = int(request.form.get("problems_per_test", 4))

    if not subject or not level:
        return "Eroare: Selectează Materie și Nivel.", 400

    total_needed = num_tests * problems_per_test
    conn = current_app.config["DB_CONN"]
    db_rows = dbmod.search_problems(conn, int(g.user["id"]), q=q, subject=subject, level=level)
    db_problems = [{"text": r["text_display"]} for r in db_rows]
    random.shuffle(db_problems)
    selected_problems = db_problems[:total_needed]

    missing = total_needed - len(selected_problems)
    if missing > 0:
        cfg = current_app.config
        ai_items = generate_multi(
            cfg["GEMINI_API_KEY"],
            cfg["GEMINI_MODEL"],
            cfg["HF_TOKEN"],
            cfg["HF_MODEL"],
            subject,
            level,
            difficulty,
            missing,
            topic=q
        )

        for source, text in ai_items:
            dbmod.insert_problem(conn, subject, level, difficulty, source, text)
            selected_problems.append({"text": text})

    random.shuffle(selected_problems)
    variants = [{"title": f"Varianta {i+1}", "problems": selected_problems[i*problems_per_test : (i+1)*problems_per_test]} for i in range(num_tests)]
    path = export_smart_test_pdf_premium(variants, subject, level)
    resp = send_file(path, as_attachment=True)
    resp.set_cookie("fileDownload", "true", max_age=10)
    dbmod.log_event(conn, int(g.user["id"]), "export_smart_test", {
    "subject": subject,
    "level": level,
    "q": q,
    "difficulty": difficulty,
    "num_tests": num_tests,
    "problems_per_test": problems_per_test
})
    return resp

# ---------------- API / ADMIN ----------------

@bp.post("/api/save_problem")
@login_required
def api_save_problem():
    data = request.get_json(force=True)
    conn = current_app.config["DB_CONN"]

    pred_level, pred_diff, pred_conf = classify_problem(data["subject"], data["text"])

    near_dup = dbmod.find_near_duplicate(
        conn,
        data["subject"],
        data["level"],
        data["difficulty"],
        data["text"],
        threshold=0.90
    )

    pid, is_dup = dbmod.insert_problem(
        conn,
        data["subject"],
        data["level"],
        data["difficulty"],
        data["source"],
        data["text"],
        pred_level,
        pred_diff,
        pred_conf
    )

    return jsonify({
        "ok": True,
        "id": pid,
        "duplicate": is_dup,
        "near_duplicate": near_dup,
        "pred_level": pred_level,
        "pred_difficulty": pred_diff,
        "pred_confidence": pred_conf
    })

@bp.post("/api/delete_problem")
@login_required
def api_delete_problem():
    pid = request.get_json(force=True).get("id")
    ok = dbmod.delete_problem(current_app.config["DB_CONN"], int(pid))
    return jsonify({"ok": ok})

@bp.post("/api/toggle_favorite")
@login_required
def api_toggle_favorite():
    pid = int(request.get_json(force=True).get("id"))
    state = dbmod.toggle_favorite(current_app.config["DB_CONN"], int(g.user["id"]), pid)
    return jsonify({"ok": True, "favorite": state})

@bp.post("/api/delete_saved_filter")
@login_required
def api_delete_saved_filter():
    fid = int(request.get_json(force=True).get("id"))
    ok = dbmod.delete_saved_filter(current_app.config["DB_CONN"], fid, int(g.user["id"]))
    return jsonify({"ok": ok})


@bp.get("/stats")
@login_required
def stats():
    conn = current_app.config["DB_CONN"]

    rows = dbmod.stats_actions(conn) if g.user["role"] == "admin" else dbmod.stats_actions_for_user(conn, int(g.user["id"]))

    summary = {
        "problems": dbmod.count_problems(conn),
        "users": dbmod.count_users(conn),
        "favorites": dbmod.count_favorites(conn),
        "generated": dbmod.count_events_by_action(conn, "generate"),
        "saved": dbmod.count_events_by_action(conn, "save_problem"),
        "smart_tests": dbmod.count_events_by_action(conn, "export_smart_test"),
    }

    return render_template(
        "stats.html",
        rows=rows,
        is_admin=(g.user["role"] == "admin"),
        summary=summary
    )

@bp.get("/admin/users")
@role_required("admin")
def admin_users():
    users = dbmod.list_users(current_app.config["DB_CONN"])
    return render_template("admin_users.html", users=users, msg=None, err=None)

@bp.post("/admin/users")
@role_required("admin")
def admin_users_post():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    role = request.form.get("role", "teacher")

    conn = current_app.config["DB_CONN"]
    ok, message = dbmod.create_user(conn, email, password, role)

    dbmod.log_event(conn, int(g.user["id"]), "create_user", {
        "email": email,
        "ok": ok,
        "role": role
    })

    users = dbmod.list_users(conn)
    if ok:
        return render_template("admin_users.html", users=users, msg="Utilizator creat.", err=None)

    return render_template("admin_users.html", users=users, msg=None, err=message)

@bp.post("/admin/users/delete")
@role_required("admin")
def admin_users_delete():
    uid = int(request.form.get("id"))
    conn = current_app.config["DB_CONN"]

    if int(g.user["id"]) == uid:
        users = dbmod.list_users(conn)
        return render_template(
            "admin_users.html",
            users=users,
            msg=None,
            err="Nu te poți șterge pe tine."
        )

    ok = dbmod.delete_user(conn, uid)

    dbmod.log_event(conn, int(g.user["id"]), "delete_user", {
        "id": uid,
        "ok": ok
    })

    users = dbmod.list_users(conn)
    return render_template(
        "admin_users.html",
        users=users,
        msg="Șters." if ok else None,
        err=None if ok else "Nu s-a putut șterge."
    )

@bp.post("/generate_similar")
@login_required
def generate_similar():
    ids = [int(x) for x in request.form.getlist("ids")]
    if not ids:
        return redirect(url_for("web.bank"))

    conn = current_app.config["DB_CONN"]
    placeholders = ",".join(["?"] * len(ids))

    rows = conn.execute(
        f"""
        SELECT subject, level, difficulty,
               COALESCE(NULLIF(text_raw,''), text) AS text_display
        FROM problems
        WHERE id IN ({placeholders})
        """,
        ids
    ).fetchall()

    if not rows:
        return redirect(url_for("web.bank"))

    subject = rows[0]["subject"]
    level = rows[0]["level"]
    difficulty = rows[0]["difficulty"]
    examples = [r["text_display"] for r in rows]

    cfg = current_app.config
    items = generate_similar_multi(
        cfg["GEMINI_API_KEY"],
        cfg["GEMINI_MODEL"],
        cfg["HF_TOKEN"],
        cfg["HF_MODEL"],
        subject,
        level,
        difficulty,
        5,
        examples
    )

    dbmod.log_event(conn, int(g.user["id"]), "generate_similar", {
        "subject": subject,
        "level": level,
        "difficulty": difficulty,
        "source_ids": ids,
        "n": 5
    })

    return render_template(
        "index.html",
        items=items,
        subject=subject,
        level=level,
        difficulty=difficulty,
        topic="probleme asemănătoare"
    )