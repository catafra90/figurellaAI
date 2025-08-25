# app/charts/routes.py
import copy
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, current_app
from app import db
from app.models import Client, ChartEntry

# ------------------- Blueprint -------------------
charts_bp = Blueprint("charts", __name__)

# ------------------- constants -------------------
EXPECTED_TABS = ['profile', 'measures', 'nutrition', 'communication']

DEFAULT_ROWS = {
    'nutrition': [{'Date': '', 'Type': '', 'Notes': ''}],
    'communication': [{'comm_date': '', 'comm_type': '', 'comm_notes': ''}],
}

# ───────── Include KG/Tools in saved history rows ─────────
HISTORY_FIELDS = ("Workout", "KG", "Tools", "Rings", "Notes")

def _clean_workout_row(r: dict) -> dict:
    """Keep only the fields we want in history, fill missing with ''."""
    return {k: (r.get(k) or "") for k in HISTORY_FIELDS}


# ───────── Workout Rev History: SAVE (includes KG & Tools) ─────────
@charts_bp.post("/client/<client>/workout-rev-history/save")
def save_workout_rev_history(client: str):
    payload = request.get_json(silent=True) or {}
    raw_rows = payload.get("rows") or []

    # Normalize rows to include Workout, KG, Tools, Rings, Notes
    snapshot_rows = [_clean_workout_row(r) for r in raw_rows]

    snapshot_id = str(uuid4())
    # Store UTC; render local with Jinja filter
    label = datetime.now(timezone.utc).isoformat()

    snapshot_doc = {
        "meta": {
            "snapshot_id": snapshot_id,
            "type": "workout_rev",
            "created_at": label,
        },
        "rows": snapshot_rows,
    }

    entry = ChartEntry(
        client_name=client,
        sheet="workout_rev_history",
        data=snapshot_doc,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify(status="success", snapshot_id=snapshot_id, label=label)


# ───────── Workout Rev History: VIEW (renders the template) ─────────
@charts_bp.get("/client/<client>/workout-rev-history")
def view_workout_rev_history(client: str):
    # Pull all history docs for this client
    entries = (
        ChartEntry.query
                  .filter_by(client_name=client, sheet="workout_rev_history")
                  .order_by(ChartEntry.created_at.desc())
                  .all()
    )

    history_entries = []
    for e in entries:
        doc = (e.data or {})
        meta = doc.get("meta", {})
        label = meta.get("created_at") or (
            # Fallback to the DB timestamp if needed
            (e.created_at.astimezone(timezone.utc).isoformat() if e.created_at else "")
        )
        history_entries.append({
            "meta": {
                "snapshot_id": meta.get("snapshot_id", ""),
                "type": meta.get("type", "workout_rev"),
            },
            "label": label,          # UTC string, formatted in template with |format_est
            "rows": doc.get("rows", [])
        })

    return render_template(
        "charts/workout_rev_history.html",
        client_name=client,
        history_entries=history_entries,
    )


# ───────── Workout Rev History: DELETE (portable across DBs) ─────────
@charts_bp.post("/client/<client>/workout-rev-history/<snapshot_id>/delete")
def delete_workout_rev_history(client: str, snapshot_id: str):
    # Portable approach (SQLite/Postgres): fetch and match in Python
    rows = (
        ChartEntry.query
                  .filter_by(client_name=client, sheet="workout_rev_history")
                  .all()
    )
    target = None
    for r in rows:
        try:
            if (r.data or {}).get("meta", {}).get("snapshot_id") == snapshot_id:
                target = r
                break
        except Exception:
            continue

    if not target:
        return jsonify(status="not_found"), 404

    db.session.delete(target)
    db.session.commit()
    return jsonify(status="success")





# ------------------- WORKOUT BLOCKS -------------------
# ---- C1–C5 ----
C1_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "PUSH LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "FROG", "Rings": "S", "Notes": ""},
        {"Workout": "KICKS SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "KICK SIDE TURN", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE TRIANGLES", "Rings": "S+S", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "S+S", "Notes": ""},
        {"Workout": "1 LEG FROG", "Rings": "IOP", "Notes": ""},
        {"Workout": "BENDING LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS BACK", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS BACK/UP", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "ROW SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "TRICEPS OPP", "Rings": "Sop", "Notes": ""},
    ],
    "GK": []
}
C2_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP 90", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "BICYCLE", "Rings": "S", "Notes": ""},
        {"Workout": "LEGS EXTENSION", "Rings": "S", "Notes": ""},
        {"Workout": "CROSSED KICKS", "Rings": "Sop", "Notes": ""},
        {"Workout": "1 LEG FROG UP/DOWN", "Rings": "Iop", "Notes": ""},
        {"Workout": "SIDE BICYCLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE KICK CHEST", "Rings": "I", "Notes": ""},
        {"Workout": "HIPS UP", "Rings": "-", "Notes": ""},
        {"Workout": "1/2 KICKS BACK", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE STR.", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 KICKS ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER UP", "Rings": "-", "Notes": ""},
        {"Workout": "ARMS LIFT L.D.", "Rings": "S", "Notes": ""},
        {"Workout": "BACK BUTTERFLY SEAT", "Rings": "I", "Notes": ""},
        {"Workout": "PUSH ARMS UP", "Rings": "S", "Notes": ""},
    ], "GK": []
}
C3_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP ALT", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST STRAIGHT", "Rings": "S", "Notes": ""},
        {"Workout": "DOUBLE KICKS TURN", "Rings": "S", "Notes": ""},
        {"Workout": "FROGGY", "Rings": "S", "Notes": ""},
        {"Workout": "DIAGONAL KICKS", "Rings": "I", "Notes": ""},
        {"Workout": "LEGS EXTENSION ALT", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 KICK SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE BEND & EXTEND", "Rings": "I", "Notes": ""},
        {"Workout": "SWAY", "Rings": "-", "Notes": ""},
        {"Workout": "PELVIS UP", "Rings": "-", "Notes": ""},
        {"Workout": "CIRCLES ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 TRIANGLES O.K.", "Rings": "I", "Notes": ""},
        {"Workout": "BOXING", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE ARM TURN", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED ROW", "Rings": "Iop", "Notes": ""},
        {"Workout": "TRIC OPP SEATED", "Rings": "Iop", "Notes": ""},
    ], "GK": []
}
C4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE KICKS", "Rings": "-", "Notes": ""},
        {"Workout": "FETAL CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "DOUBLE PUSH LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "REVERSE BICYCLE", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE KICKS PUMP", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE TURN REV", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "1 LEG FROG OP/CL", "Rings": "Iop", "Notes": ""},
        {"Workout": "CAT UP", "Rings": "-", "Notes": ""},
        {"Workout": "BENDING LEGS ALT", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE", "Rings": "s+s", "Notes": ""},
        {"Workout": "BEND/EXTEND ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER ELBOW B.D.", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS TWIST", "Rings": "Iop", "Notes": ""},
    ], "GK": []
}
C5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "DOUBLE KICKS TURN REV", "Rings": "S", "Notes": ""},
        {"Workout": "ALT FROG", "Rings": "S", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "TRIANGLES ON STOM", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 CIRCLES ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "TRIANGLES ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS OPP", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
    ], "GK": []
}

# ---- V1–V5 ----
V1_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "PUSH LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "FROG", "Rings": "S", "Notes": ""},
        {"Workout": "BICYCLE", "Rings": "S", "Notes": ""},
        {"Workout": "HIPS UP", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS UP", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE TURN", "Rings": "I", "Notes": ""},
        {"Workout": "BENDING LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS BACK", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS BACK/UP", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "ROW SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "TRICEPS OPP", "Rings": "Sop", "Notes": ""},
    ], "GK": []
}
V2_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP 90", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "S", "Notes": ""},
        {"Workout": "EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "SWAY", "Rings": "-", "Notes": ""},
        {"Workout": "STOMACH UP/DOWN", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TO CHEST", "Rings": "I", "Notes": ""},
        {"Workout": "LEGS EXTENSION", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE TRIANGLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS ON KNEE STR", "Rings": "I", "Notes": ""},
        {"Workout": "1/2 KICKS ON KNEE", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER UP", "Rings": "-", "Notes": ""},
        {"Workout": "ARMS LIFT L.D.", "Rings": "S", "Notes": ""},
        {"Workout": "BACK BUTTERFLY SEAT", "Rings": "I", "Notes": ""},
        {"Workout": "PUSH ARMS UP", "Rings": "S", "Notes": ""},
    ], "GK": []
}
V3_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP ALT", "Rings": "-", "Notes": ""},
        {"Workout": "REVERSE CRUNCH", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST STRAIGHT", "Rings": "S", "Notes": ""},
        {"Workout": "ELBOW KNEE STS", "Rings": "I", "Notes": ""},
        {"Workout": "KICK UP TOUCH", "Rings": "I", "Notes": ""},
        {"Workout": "LATERAL KICKS (inner)", "Rings": "I", "Notes": ""},
        {"Workout": "STOMACH TRIANGLES", "Rings": "-", "Notes": ""},
        {"Workout": "1/2 KICK SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE BEND & EXTEND", "Rings": "I", "Notes": ""},
        {"Workout": "CHEST LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "BOXING", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE ARM TURN", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED ROW", "Rings": "Iop", "Notes": ""},
        {"Workout": "TRIC OPP SEATED", "Rings": "Iop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ], "GK": []
}
V4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE KICKS", "Rings": "-", "Notes": ""},
        {"Workout": "FETAL CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "REVERSE EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST U", "Rings": "I", "Notes": ""},
        {"Workout": "CAT UP", "Rings": "-", "Notes": ""},
        {"Workout": "CLIMBER", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS SIDE TURN REV", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES ALT", "Rings": "I", "Notes": ""},
        {"Workout": "KICK DIAGONAL COMPL", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER ELBOW B.D.", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ], "GK": []
}
V5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ], "GK": []
}

# ---- TO1–TO5 ----
TO1_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "S", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "S", "Notes": ""},
        {"Workout": "EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "HIPS UP", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS UP", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS SIDE TURN", "Rings": "I", "Notes": ""},
        {"Workout": "SUPERWOMAN", "Rings": "ALL", "Notes": ""},
        {"Workout": "BODY TWIST", "Rings": "Sop", "Notes": ""},
        {"Workout": "ARMS BACK/UP", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "ROW SEATED", "Rings": "I", "Notes": ""},
        {"Workout": "TRICEPS OPP", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
}
TO2_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP 90", "Rings": "-", "Notes": ""},
        {"Workout": "1 LEG TWIST", "Rings": "I", "Notes": ""},
        {"Workout": "HIPS SIDE TO SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "ELBOW KNEE (feet down)", "Rings": "-", "Notes": ""},
        {"Workout": "SWAY", "Rings": "-", "Notes": ""},
        {"Workout": "STOMACH UP/DOWN", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TO CHEST", "Rings": "I", "Notes": ""},
        {"Workout": "KICKS DIAGONAL", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE TRIANGLES", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "HIPS SIDE TO SIDE BD", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER UP", "Rings": "-", "Notes": ""},
        {"Workout": "ARMS LIFT L.D.", "Rings": "S", "Notes": ""},
        {"Workout": "BACK BUTTERFLY SEAT", "Rings": "I", "Notes": ""},
        {"Workout": "PUSH ARMS UP", "Rings": "S", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
}
TO3_BLOCK = {
    "rows": [
        {"Workout": "CHEST UP ALT", "Rings": "-", "Notes": ""},
        {"Workout": "REVERSE CRUNCH", "Rings": "-", "Notes": ""},
        {"Workout": "KNEES TWIST STRAIGHT", "Rings": "S", "Notes": ""},
        {"Workout": "KICK UP ALT", "Rings": "S", "Notes": ""},
        {"Workout": "ELBOW KNEE STS", "Rings": "I", "Notes": ""},
        {"Workout": "KICK UP TOUCH", "Rings": "I", "Notes": ""},
        {"Workout": "LATERAL KICKS (inner)", "Rings": "I", "Notes": ""},
        {"Workout": "STOMACH TRIANGLES", "Rings": "-", "Notes": ""},
        {"Workout": "1/2 KICK SIDE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE BEND & EXTEND", "Rings": "I", "Notes": ""},
        {"Workout": "CHEST LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "BOXING", "Rings": "S", "Notes": ""},
        {"Workout": "SIDE ARM TURN", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED ROW", "Rings": "Iop", "Notes": ""},
        {"Workout": "TRIC OPP SEATED", "Rings": "Iop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],
    }
TO4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE KICKS", "Rings": "-", "Notes": ""},
        {"Workout": "FETAL CHEST UP", "Rings": "-", "Notes": ""},
        {"Workout": "ELBOW KNEES", "Rings": "S", "Notes": ""},
        {"Workout": "REVERSE EAGLE", "Rings": "S", "Notes": ""},
        {"Workout": "SCISSORS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST U", "Rings": "I", "Notes": ""},
        {"Workout": "CAT UP", "Rings": "-", "Notes": ""},
        {"Workout": "CLIMBER", "Rings": "-", "Notes": ""},
        {"Workout": "KICKS SIDE TURN REV", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE CIRCLES ALT", "Rings": "I", "Notes": ""},
        {"Workout": "KICK DIAGONAL COMPL", "Rings": "I", "Notes": ""},
        {"Workout": "SHOULDER ELBOW B.D.", "Rings": "S", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "BICEPS TWIST", "Rings": "Iop", "Notes": ""},
        {"Workout": "ARMS LIFT", "Rings": "S", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ],

    }
TO5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B1_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B2_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B3_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B4_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B5_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B6_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B7_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B8_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B9_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B10_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B11_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }

B12_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }


B13_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }


B14_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }


B15_BLOCK = {
    "rows": [
        {"Workout": "DOUBLE TWIST", "Rings": "-", "Notes": ""},
        {"Workout": "CHEST UP 3 90", "Rings": "-", "Notes": ""},
        {"Workout": "FEET KICKS & CIRCLES", "Rings": "I", "Notes": ""},
        {"Workout": "CROSSED LEGS", "Rings": "I", "Notes": ""},
        {"Workout": "KNEES TO CHEST ALT", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE LEGS LIFT", "Rings": "-", "Notes": ""},
        {"Workout": "HIPS SEMICIRCLE", "Rings": "-", "Notes": ""},
        {"Workout": "INNER THIGHS", "Rings": "I+I", "Notes": ""},
        {"Workout": "SIDE 1/2 TRIANGLE", "Rings": "I", "Notes": ""},
        {"Workout": "SIDE PUSH", "Rings": "Sop", "Notes": ""},
        {"Workout": "CHEST LIFT U", "Rings": "-", "Notes": ""},
        {"Workout": "SIDE ARM BACK", "Rings": "Sop", "Notes": ""},
        {"Workout": "BICEPS DIAGONAL", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ARMS UP SEATED", "Rings": "S/I", "Notes": ""},
        {"Workout": "CROSS ROW OK", "Rings": "Sop", "Notes": ""},
        {"Workout": "", "Rings": "", "Notes": ""},
    ]
   }


# Collect all blocks for template / JSON use
WORKOUT_FALLBACKS = {
    "C1": C1_BLOCK, "C2": C2_BLOCK, "C3": C3_BLOCK, "C4": C4_BLOCK, "C5": C5_BLOCK,
    "V1": V1_BLOCK, "V2": V2_BLOCK, "V3": V3_BLOCK, "V4": V4_BLOCK, "V5": V5_BLOCK,
    "TO1": TO1_BLOCK, "TO2": TO2_BLOCK, "TO3": TO3_BLOCK, "TO4": TO4_BLOCK, "TO5": TO5_BLOCK, 
    "B1": B1_BLOCK, "B2": B2_BLOCK, "B3": B3_BLOCK, "B4": B4_BLOCK, "B5": B5_BLOCK, "B6": B6_BLOCK, "B7": B7_BLOCK, 
    "B8": B8_BLOCK, "B9": B9_BLOCK, "B10": B10_BLOCK, "B11": B11_BLOCK, "B12": B12_BLOCK, "B13": B13_BLOCK, "B14": B14_BLOCK, "B15": B15_BLOCK
}


# ---------- template folder detection ----------
_here = Path(__file__).resolve()
TEMPLATES_DIR = (_here.parent.parent / "templates").resolve()
if not (TEMPLATES_DIR / "charts").exists():
    TEMPLATES_DIR = (_here.parent.parent / "template").resolve()

charts_bp = Blueprint(
    "charts",
    __name__,
    url_prefix="/charts",
    template_folder=str(TEMPLATES_DIR)
)


# ------------------- small helpers -------------------
def _truthy(val) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val or '').strip().lower()
    return s not in ('', 'no', 'false', '0', 'off', 'none')


def _bulk_quick_flags(client_names):
    flags = {name: {'nutrition': False, 'focus': False} for name in client_names}
    if not client_names:
        return flags
    try:
        rows = (ChartEntry.query
                .filter(ChartEntry.client_name.in_(client_names),
                        ChartEntry.sheet == 'profile')
                .order_by(ChartEntry.created_at.desc())
                .all())
        seen = {name: {'nutrition': False, 'focus': False} for name in client_names}
        for ent in rows:
            data = ent.data or {}
            field = (data.get('Field') or '').strip()
            if ent.client_name not in flags:
                continue
            if field == 'Nutrition Flag' and not seen[ent.client_name]['nutrition']:
                flags[ent.client_name]['nutrition'] = _truthy(data.get('Flag') or data.get('Value'))
                seen[ent.client_name]['nutrition'] = True
            elif field == 'Focus Case Flag' and not seen[ent.client_name]['focus']:
                flags[ent.client_name]['focus'] = _truthy(data.get('Flag') or data.get('Value'))
                seen[ent.client_name]['focus'] = True
    except Exception as e:
        current_app.logger.error(f"[charts/_bulk_quick_flags] {e}")
    return flags


def _rows_from_sheet_obj(sheet_obj):
    if isinstance(sheet_obj, dict) and isinstance(sheet_obj.get('data'), list):
        return sheet_obj['data']
    if isinstance(sheet_obj, list):
        return sheet_obj
    return None


def _is_m_field(val: str) -> bool:
    return isinstance(val, str) and (val.startswith('M0:') or val.startswith('M2:') or val.startswith('M3:'))


def _utc_iso(dt: datetime | None = None) -> str:
    """Return UTC ISO 8601 string."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


# ------------------- views -------------------
@charts_bp.route("/", methods=["GET"])
def view_charts():
    filter_status = (request.args.get('status') or '').strip()
    filter_client = (request.args.get('client') or '').strip()
    filter_applied = False
    try:
        if filter_client and not filter_status:
            c = Client.query.filter_by(name=filter_client).first()
            if c and c.status:
                filter_status = c.status.strip()

        q = Client.query
        if filter_status:
            filter_applied = True
            q = q.filter(db.func.lower(Client.status) == filter_status.lower())

        clients = q.order_by(Client.created_at).all()

        names = [c.name for c in clients]
        flags_map = _bulk_quick_flags(names)

        columns = ['Name', 'Date Created', 'Status', 'Email', 'Phone']
        data = []
        for c in clients:
            f = flags_map.get(c.name, {'nutrition': False, 'focus': False})
            data.append({
                'Name': c.name,
                'Date Created': c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
                'Status': c.status,
                'Email': c.email or '',
                'Phone': c.phone or '',
                'Nutrition Flag': 'Yes' if f.get('nutrition') else 'No',
                'Focus Case Flag': 'Yes' if f.get('focus') else 'No',
                'nutrition_flag': f.get('nutrition'),
                'focus_flag': f.get('focus'),
            })

        return render_template(
            "charts/charts.html",
            columns=columns, data=data, error=None,
            active_page='charts',
            filter_status=filter_status, filter_applied=filter_applied, filter_client=filter_client
        )
    except Exception as e:
        current_app.logger.error(f"[view_charts] {e}")
        return render_template(
            "charts/charts.html",
            columns=[], data=[], error="Could not load client list.",
            active_page='charts',
            filter_status=filter_status, filter_applied=filter_applied, filter_client=filter_client
        )


@charts_bp.route("/client/<client>", methods=["GET"])
def client_chart(client):
    """Render the client card partial (+ blocks json for Rev1)."""
    try:
        client_obj = Client.query.filter_by(name=client).first()
        client_status = (client_obj.status if client_obj and client_obj.status else '').strip()

        sheets = {}
        for tab in EXPECTED_TABS:
            entries = (ChartEntry.query
                       .filter_by(client_name=client, sheet=tab)
                       .order_by(ChartEntry.created_at)
                       .all())
            data = [e.data for e in entries] if entries else DEFAULT_ROWS.get(tab, [])
            sheets[tab] = {'data': data}

        # Include latest "workout_rev1" grid (current editable state)
        rev1_entries = (ChartEntry.query
                        .filter_by(client_name=client, sheet='workout_rev1')
                        .order_by(ChartEntry.created_at)
                        .all())
        sheets['workout_rev1'] = {'data': [e.data for e in rev1_entries] if rev1_entries else []}

        return render_template(
            "charts/_client_form.html",
            client=client,
            client_status=client_status,
            sheets=sheets,
            workout_blocks_json=WORKOUT_FALLBACKS
        )
    except Exception as e:
        current_app.logger.error(f"[client_chart/{client}] {e}")
        return f"<div style='padding:1rem;color:#b91c1c'>Template error: {e}</div>", 200


@charts_bp.route("/blocks.json", methods=["GET"])
def blocks_json():
    """Fallback JSON endpoint so the UI can fetch plans even if scripts/templates are stripped."""
    try:
        return jsonify({"blocks": WORKOUT_FALLBACKS}), 200
    except Exception as e:
        current_app.logger.error(f"[blocks_json] {e}")
        return jsonify({"blocks": {}}), 200


@charts_bp.route("/client/<client>/save", methods=["POST"])
def save_client_chart(client):
    """
    Bulk or single‑section save for tabs.
    Accepts either:
      { "section": "<tab>", "data": [...] }
      or
      { "sheets": { "<tab>": [...], ... } }
      or
      { "<tab>": [...], "<tab2>": [...] }  (direct)
    """
    # Parse JSON
    try:
        payload = request.get_json(force=True) or {}
    except Exception as e:
        current_app.logger.error(f"[save_client_chart] JSON error: {e}")
        return jsonify(status='error', message='Invalid JSON'), 400

    # Single-section fast path
    if isinstance(payload, dict) and 'section' in payload:
        section = str(payload.get('section', '')).lower().strip()
        rows = payload.get('data') or []
        if section not in EXPECTED_TABS and section != 'workout_rev1':
            return jsonify(status='error', message=f"Unknown section '{section}'"), 400
        if not isinstance(rows, list):
            return jsonify(status='error', message='`data` must be a list'), 400

        try:
            if section == 'measures':
                existing = ChartEntry.query.filter_by(client_name=client, sheet='measures').all()
                for ent in existing:
                    field = (ent.data or {}).get('Field', '') or ''
                    if _is_m_field(field):
                        db.session.delete(ent)
                inserted = 0
                for row in rows:
                    if isinstance(row, dict) and _is_m_field(row.get('Field', '')):
                        db.session.add(ChartEntry(client_name=client, sheet='measures', data=row))
                        inserted += 1
                db.session.commit()
                return jsonify(status='success', mode='partial', sheet='measures', inserted=inserted), 200

            # Replace section entirely
            ChartEntry.query.filter_by(client_name=client, sheet=section).delete(synchronize_session=False)
            inserted = 0
            for row in rows:
                if isinstance(row, dict):
                    db.session.add(ChartEntry(client_name=client, sheet=section, data=row))
                    inserted += 1
            db.session.commit()
            return jsonify(status='success', mode='replace', sheet=section, inserted=inserted), 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"[save_client_chart/{client}] {e}")
            return jsonify(status='error', message='Database error'), 500

    # ---------- BULK SAVE ----------
    # Accept either {"sheets": {...}} or directly {...}
    if isinstance(payload, dict) and isinstance(payload.get("sheets"), dict):
        sheets_payload = payload["sheets"]
    else:
        sheets_payload = payload

    if not isinstance(sheets_payload, dict):
        return jsonify(status='error', message='Invalid payload root'), 400

    # Validate & normalize
    parsed = {}
    for sheet_name, sheet_obj in sheets_payload.items():
        sheet = str(sheet_name or '').lower()
        if sheet not in EXPECTED_TABS and sheet != 'workout_rev1':
            continue
        rows = _rows_from_sheet_obj(sheet_obj)
        if rows is None:
            continue
        parsed[sheet] = rows

    if not parsed:
        return jsonify(status='error', message='No valid sheets to save'), 400

    try:
        total = 0
        for sheet, rows in parsed.items():
            ChartEntry.query.filter_by(client_name=client, sheet=sheet).delete(synchronize_session=False)
            for row in rows:
                if isinstance(row, dict):
                    db.session.add(ChartEntry(client_name=client, sheet=sheet, data=row))
                    total += 1
        db.session.commit()
        return jsonify(status='success', mode='bulk', saved=total, sheets=list(parsed.keys())), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[save_client_chart bulk/{client}] {e}")
        return jsonify(status='error', message='Database error'), 500



# ------------------- Rev1 Submit + History -------------------

@charts_bp.route("/client/<client>/workout-rev1/submit", methods=["POST"])
def workout_rev1_submit(client):
    """
    Save the current Rev1 grid AND create a history snapshot.
    Request JSON:
      {
        "rows": [{Workout, Rings, Notes} * 16],
        "kg": "...", "tools": "...", "program_type": "C1|...|TO5",
        "gk_rows": [...]  // optional, if present
      }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception as e:
        current_app.logger.error(f"[workout_rev1_submit/{client}] JSON error: {e}")
        return jsonify(status='error', message='Invalid JSON'), 400

    rows         = data.get("rows") or []
    gk_rows      = data.get("gk_rows") or []
    kg_default   = (data.get("kg") or "").strip()
    tools_default= (data.get("tools") or "").strip()
    program_type = (data.get("program_type") or "").strip()

    if not isinstance(rows, list):
        return jsonify(status='error', message='`rows` must be a list'), 400

    # ---- 1) Replace the current editable grid (sheet='workout_rev1') ----
    try:
        ChartEntry.query.filter_by(client_name=client, sheet='workout_rev1').delete(synchronize_session=False)
        for row in rows:
            if isinstance(row, dict):
                db.session.add(ChartEntry(client_name=client, sheet='workout_rev1', data=row))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[workout_rev1_submit replace/{client}] {e}")
        return jsonify(status='error', message='Failed to save current grid'), 500

    # ---- 2) Build per-row data INCLUDING KG & Tools (defaults from toolbar) ----
    def _merge(r: dict) -> dict:
        return {
            "Workout": (r.get("Workout") or "").strip(),
            "KG":      (r.get("KG") or kg_default or "").strip(),
            "Tools":   (r.get("Tools") or tools_default or "").strip(),
            "Rings":   (r.get("Rings") or "").strip(),
            "Notes":   (r.get("Notes") or "").strip(),
        }

    def _has_any(row: dict) -> bool:
        return any((row.get(k) or "").strip() for k in ("Workout", "KG", "Tools", "Rings", "Notes"))

    main_rows = [_merge(r) for r in rows]
    main_rows = [r for r in main_rows if _has_any(r)]

    gk_norm = [_merge(r) for r in (gk_rows if isinstance(gk_rows, list) else [])]
    gk_norm = [r for r in gk_norm if _has_any(r)]

    snapshot_rows = main_rows + gk_norm

    # ---- 3) Insert the snapshot (sheet='workout_rev1_history') ----
    snapshot = {
        "snapshot_id": str(uuid4()),
        "snapshot_at": _utc_iso(),
        "kg": kg_default,            # keep in meta too (nice to display/filter later)
        "tools": tools_default,
        "program_type": program_type,
        "rows": snapshot_rows,       # <-- rows now have KG/Tools per row
    }

    try:
        db.session.add(ChartEntry(client_name=client, sheet='workout_rev1_history', data=snapshot))
        db.session.commit()
        return jsonify(status='success', snapshot=snapshot), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[workout_rev1_submit snapshot/{client}] {e}")
        return jsonify(status='error', message='Failed to create history snapshot'), 500


@charts_bp.route("/client/<client>/workout-rev-history.json", methods=["GET"])
def workout_rev_history_json(client):
    """
    Return a list of snapshot entries for this client (newest first).
    Each item includes: snapshot_id, snapshot_at, kg, tools, program_type, rows.
    """
    try:
        entries = (ChartEntry.query
                   .filter_by(client_name=client, sheet='workout_rev1_history')
                   .order_by(ChartEntry.created_at.desc())
                   .all())

        snapshots = []
        for ent in entries:
            d = ent.data or {}
            # Coerce timestamp
            snap_at = d.get("snapshot_at") or _utc_iso(ent.created_at)
            snapshots.append({
                "snapshot_id": d.get("snapshot_id") or str(ent.id),
                "snapshot_at": snap_at,
                "kg": d.get("kg", ""),
                "tools": d.get("tools", ""),
                "program_type": d.get("program_type", ""),
                "rows": d.get("rows", []),
            })

        return jsonify(status='success', snapshots=snapshots, count=len(snapshots)), 200
    except Exception as e:
        current_app.logger.error(f"[workout_rev_history_json/{client}] {e}")
        return jsonify(status='error', message='Failed to load history'), 500


# (Optional) Keep a simple HTML history page (handy for direct link or debugging)
@charts_bp.route("/client/<client>/workout-rev-history", methods=["GET"], endpoint="workout_rev_history")
def workout_rev_history_page(client):
    try:
        entries = (ChartEntry.query
                   .filter_by(client_name=client, sheet='workout_rev1_history')
                   .order_by(ChartEntry.created_at.desc())
                   .all())

        history_entries = []
        for ent in entries:
            d = ent.data or {}
            history_entries.append({
                "label": (d.get("snapshot_at") or _utc_iso(ent.created_at)),
                "rows": d.get("rows", []),
                "meta": {
                    "kg": d.get("kg", ""),
                    "tools": d.get("tools", ""),
                    "program_type": d.get("program_type", ""),
                    # include snapshot_id for actions (delete, etc.)
                    "snapshot_id": d.get("snapshot_id") or str(ent.id),
                }
            })
        return render_template(
            "charts/workout_rev_history.html",
            client_name=client,
            history_entries=history_entries
        )
    except Exception as e:
        current_app.logger.error(f"[workout_rev_history_page/{client}] {e}")
        return f"<div style='padding:1rem;color:#b91c1c'>History view error: {e}</div>", 200


@charts_bp.post("/client/<client>/workout-rev1/clear")
def clear_workout_rev1(client: str):
    """
    Hard-clear current editable grid (sheet='workout_rev1') for this client.
    Write back 16 blank rows so subsequent loads stay empty.
    """
    try:
        # nuke existing rows
        ChartEntry.query.filter_by(client_name=client, sheet='workout_rev1')\
                        .delete(synchronize_session=False)

        # write 16 blank rows so UI stays empty after reload
        for _ in range(20):
            db.session.add(ChartEntry(
                client_name=client,
                sheet='workout_rev1',
                data={"Workout": "", "Rings": "", "Notes": ""}
            ))
        db.session.commit()
        return jsonify(status="success"), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[clear_workout_rev1/{client}] {e}")
        return jsonify(status="error", message="Failed to clear"), 500




@charts_bp.route("/client/<client>/workout-rev-history/<snapshot_id>/delete", methods=["POST"])
def delete_workout_rev_history(client, snapshot_id):
    """
    Delete a specific workout_rev1_history snapshot by its snapshot_id.

    - Primary key is data['snapshot_id'] (uuid4 at submit time).
    - For older rows that may not have snapshot_id, we fall back to the row's DB id.
    """
    try:
        candidates = (ChartEntry.query
                      .filter_by(client_name=client, sheet='workout_rev1_history')
                      .all())

        target = None
        for ent in candidates:
            d = ent.data or {}
            sid = d.get("snapshot_id") or str(ent.id)
            if sid == snapshot_id:
                target = ent
                break

        if not target:
            return jsonify(status="error", message="Snapshot not found"), 404

        db.session.delete(target)
        db.session.commit()
        return jsonify(status="success", deleted=1, snapshot_id=snapshot_id), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[delete_workout_rev_history/{client}] {e}")
        return jsonify(status="error", message="Failed to delete snapshot"), 500


# ───────────────── GK (Goldorack) row order: LOAD ─────────────────
@charts_bp.route("/client/<client>/gk-order.json", methods=["GET"])
def charts_get_gk_order(client):
    """Return saved GK row order for this client."""
    row = (
        ChartEntry.query
        .filter_by(client_name=client, sheet="gk_order")
        .order_by(ChartEntry.created_at.desc())
        .first()
    )
    data = row.data if row and isinstance(row.data, dict) else {}
    return jsonify({"order": data.get("order", [])})

# ───────────────── GK (Goldorack) row order: SAVE ─────────────────
@charts_bp.route("/client/<client>/gk-order", methods=["POST"])
def charts_save_gk_order(client):
    """Persist current GK order (list of workout names in visual order)."""
    payload = request.get_json(silent=True) or {}
    order = payload.get("order", [])
    # upsert one row per client
    ChartEntry.query.filter_by(client_name=client, sheet="gk_order").delete(synchronize_session=False)
    db.session.add(ChartEntry(
        client_name=client,
        sheet="gk_order",
        data={"order": order, "saved_at": datetime.now(timezone.utc).isoformat()}
    ))
    db.session.commit()
    return jsonify({"ok": True})
