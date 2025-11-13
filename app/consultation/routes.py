# app/consultation/routes.py
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import base64, re, sqlite3
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, make_response

bp = Blueprint("consultation", __name__, url_prefix="/consultation")
# Export alias to match your create_app import
consultation_bp = bp

# ---------- DB helpers ----------
def _db_path() -> Path:
    inst = Path(current_app.instance_path)
    inst.mkdir(parents=True, exist_ok=True)
    return inst / "figurella.db"

def _conn():
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    # future-proof for FKs
    try:
        con.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return con

def _init_db():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS clients(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          first_name TEXT, last_name TEXT,
          goals TEXT, needs TEXT, benefits TEXT,
          ideal_program TEXT, suggestion TEXT, other_options TEXT,
          signature_path TEXT,
          created_at TEXT
        );
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS commitments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_id INTEGER NOT NULL,
          init_showup TEXT,
          init_appointments TEXT,
          init_speakup TEXT,
          init_honest TEXT,
          init_method TEXT,
          init_responsibility TEXT,
          init_respect TEXT,
          init_progress TEXT,
          init_partner TEXT,
          signature_text TEXT,
          signed_date TEXT,
          created_at TEXT,
          FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        """)

def _save_signature(data_url: str, client_id: int) -> str | None:
    if not data_url:
        return None
    m = re.match(r"^data:image/(png|jpeg);base64,(.+)$", data_url)
    if not m:
        return None
    ext = "png" if m.group(1) == "png" else "jpg"
    raw = base64.b64decode(m.group(2))
    out_dir = Path(current_app.instance_path) / "uploads" / "signatures"
    out_dir.mkdir(parents=True, exist_ok=True)
    outfile = out_dir / f"client_{client_id}.{ext}"
    outfile.write_bytes(raw)
    return str(outfile)

# ---------- Flask 3.x friendly init ----------
@bp.record_once
def _on_register(state):
    app = state.app
    with app.app_context():
        try:
            _init_db()
            app.logger.info("consultation: DB initialized")
        except Exception as e:
            app.logger.warning(f"consultation: DB init failed: {e}")

# ---------- Routes ----------
@bp.get("/")
def index():
    with _conn() as c:
        rows = c.execute(
            "SELECT id, first_name, last_name, created_at FROM clients ORDER BY id DESC"
        ).fetchall()
    return render_template("consultation/index.html", clients=rows)

@bp.post("/submit")
def submit():
    f = request.form
    fields = {
        "first_name": f.get("first_name","").strip(),
        "last_name":  f.get("last_name","").strip(),
        "goals":      f.get("goals","").strip(),
        "needs":      f.get("needs","").strip(),
        "benefits":   f.get("benefits","").strip(),
        "ideal_program": f.get("ideal_program","").strip(),
        "suggestion": f.get("suggestion","").strip(),
        "other_options": f.get("other_options","").strip(),
    }

    # guard
    if not (fields["first_name"] or fields["last_name"]):
        flash("Please enter at least a first or last name.", "warning")
        return redirect(url_for("consultation.index"))

    try:
        with _conn() as c:
            cur = c.execute("""
                INSERT INTO clients(first_name,last_name,goals,needs,benefits,ideal_program,suggestion,other_options,created_at)
                VALUES(:first_name,:last_name,:goals,:needs,:benefits,:ideal_program,:suggestion,:other_options,:created_at)
            """, {**fields, "created_at": datetime.utcnow().isoformat()})
            new_id = cur.lastrowid

            # save signature within the SAME connection to avoid Windows SQLite locks
            sig_path = _save_signature(request.form.get("signature_data",""), new_id)
            if sig_path:
                c.execute("UPDATE clients SET signature_path=? WHERE id=?", (sig_path, new_id))

        flash("Consultation saved.", "success")
        return redirect(url_for("consultation.client_profile", client_id=new_id))

    except Exception:
        current_app.logger.exception("consultation.submit failed")
        flash("Error saving consultation. Please try again.", "danger")
        return redirect(url_for("consultation.index"))

@bp.get("/client/<int:client_id>")
def client_profile(client_id: int):
    with _conn() as c:
        client = c.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        commitment = c.execute("""
            SELECT * FROM commitments
            WHERE client_id=?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
        """, (client_id,)).fetchone()
    if not client:
        flash("Client not found.", "warning")
        return redirect(url_for("consultation.index"))

    return render_template(
        "consultation/client_profile.html",
        client=client,
        client_name=f"{client['first_name']} {client['last_name']}".strip(),
        commitment=commitment
    )

@bp.post("/client/<int:client_id>/commitment")
def save_commitment(client_id: int):
    f = request.form
    payload = {
        "client_id": client_id,
        "init_showup": f.get("init_showup","").strip(),
        "init_appointments": f.get("init_appointments","").strip(),
        "init_speakup": f.get("init_speakup","").strip(),
        "init_honest": f.get("init_honest","").strip(),
        "init_method": f.get("init_method","").strip(),
        "init_responsibility": f.get("init_responsibility","").strip(),
        "init_respect": f.get("init_respect","").strip(),
        "init_progress": f.get("init_progress","").strip(),
        "init_partner": f.get("init_partner","").strip(),
        "signature_text": f.get("signature","").strip(),
        "signed_date": f.get("date","").strip(),
        "created_at": datetime.utcnow().isoformat(),
    }
    with _conn() as c:
        c.execute("""
            INSERT INTO commitments(
              client_id, init_showup, init_appointments, init_speakup, init_honest,
              init_method, init_responsibility, init_respect, init_progress, init_partner,
              signature_text, signed_date, created_at
            ) VALUES (
              :client_id, :init_showup, :init_appointments, :init_speakup, :init_honest,
              :init_method, :init_responsibility, :init_respect, :init_progress, :init_partner,
              :signature_text, :signed_date, :created_at
            )
        """, payload)

    flash("Commitment saved.", "success")
    return redirect(url_for("consultation.client_profile", client_id=client_id))

# ---------- Delete client (+ commitments + signature file) ----------
@bp.post("/client/<int:client_id>/delete")
def delete_client(client_id: int):
    with _conn() as c:
        row = c.execute("SELECT signature_path FROM clients WHERE id=?", (client_id,)).fetchone()
        c.execute("DELETE FROM commitments WHERE client_id=?", (client_id,))
        c.execute("DELETE FROM clients WHERE id=?", (client_id,))

    # best-effort file cleanup
    try:
        if row and row["signature_path"]:
            p = Path(row["signature_path"])
            if p.exists():
                p.unlink(missing_ok=True)
    except Exception:
        pass

    # If this was called via fetch() from the popup, avoid redirect
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
       "application/json" in (request.headers.get("Accept") or ""):
        return make_response(("", 204))

    flash("Contact deleted.", "success")
    return redirect(url_for("consultation.index"))

# ---------- Lazy-loaded HTML for the popup list ----------
@bp.get("/_clients/list")
def clients_list_partial():
    """Return the server-rendered HTML of the current clients list (for the popup)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT id, first_name, last_name, created_at FROM clients ORDER BY id DESC"
        ).fetchall()
    return render_template("consultation/_clients_list.html", clients=rows)
