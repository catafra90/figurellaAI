# app/charts/routes.py
import os
from flask import Blueprint, render_template, request, jsonify, current_app

from app import db
from app.models import Client, ChartEntry

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
EXPECTED_TABS = ['profile', 'measures', 'workout', 'nutrition', 'communication']

# Provide only minimal defaults used for empty renders
DEFAULT_ROWS = {
    'nutrition': [ {'Date':'', 'Type':'', 'Notes':''} ],
    'communication': [ {'comm_date':'', 'comm_type':'', 'comm_notes':''} ],
    # Workout renders its own fixed 17+4 rows via the template's loops.
    # Profile/Measures render via their own partials based on saved rows.
}

# ------------------------------------------------------------------
# Blueprint setup
# ------------------------------------------------------------------
charts_bp = Blueprint(
    'charts',
    __name__,
    url_prefix='/charts',
    template_folder=os.path.join(os.pardir, 'templates')
)

# ------------------------------------------------------------------
# Helpers (local)
# ------------------------------------------------------------------
def _normalize_status(s: str) -> str:
    """Lower/strip a status string safely for comparisons."""
    if not isinstance(s, str):
        return ''
    return s.strip().lower()

def _truthy(val) -> bool:
    """
    Interpret various stored flag values as boolean.
    Accepts True/False, 'Yes'/'No', '1'/'0', etc.
    """
    if isinstance(val, bool):
        return val
    s = str(val or '').strip().lower()
    return s not in ('', 'no', 'false', '0', 'off', 'none')

def _bulk_quick_flags(client_names):
    """
    Fetch Nutrition/Focus flags for many clients in one pass.
    Returns: { 'Client Name': {'nutrition': bool, 'focus': bool}, ... }
    """
    flags = {name: {'nutrition': False, 'focus': False} for name in client_names}
    if not client_names:
        return flags

    try:
        # Grab all 'profile' rows for these clients, newest first
        rows = (ChartEntry.query
                .filter(ChartEntry.client_name.in_(client_names),
                        ChartEntry.sheet == 'profile')
                .order_by(ChartEntry.created_at.desc())
                .all())

        # Since we ordered newest first, first time we see a flag for a client wins
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

            # early exit if we already have both flags for this client
            if seen[ent.client_name]['nutrition'] and seen[ent.client_name]['focus']:
                # small micro‑opt: do nothing special; loop continues for others
                pass

    except Exception as e:
        current_app.logger.error(f"[charts/_bulk_quick_flags] error: {e}")

    return flags

# ------------------------------------------------------------------
# Sidebar: list clients (optionally filter by status or by a client's status)
# ------------------------------------------------------------------
@charts_bp.route('/', methods=['GET'])
def view_charts():
    """
    Optional filters:
      - ?status=<Status>        → show only clients with this status
      - ?client=<Client Name>   → look up client's status and filter by it

    If no filter is present, shows all clients (original behavior).
    """
    filter_status = (request.args.get('status') or '').strip()
    filter_client = (request.args.get('client') or '').strip()
    filter_applied = False

    try:
        # If a client was specified, pull their status (unless explicit status already provided)
        if filter_client and not filter_status:
            chosen = Client.query.filter_by(name=filter_client).first()
            if chosen and chosen.status:
                filter_status = chosen.status.strip()
                current_app.logger.info(f"[charts] Using status '{filter_status}' from client '{filter_client}'")

        # Build the query, optionally filtering by status (case-insensitive)
        query = Client.query
        if filter_status:
            filter_applied = True
            query = query.filter(db.func.lower(Client.status) == filter_status.lower())

        clients_list = query.order_by(Client.created_at).all()

        # --- NEW: bulk fetch quick flags for all listed clients -------------
        names = [c.name for c in clients_list]
        flags_map = _bulk_quick_flags(names)

        columns = ['Name', 'Date Created', 'Status', 'Email', 'Phone']
        data = []
        for c in clients_list:
            flags = flags_map.get(c.name, {'nutrition': False, 'focus': False})
            data.append({
                'Name':               c.name,
                'Date Created':       c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
                'Status':             c.status,
                'Email':              c.email or '',
                'Phone':              c.phone or '',
                # Extra fields (not in `columns`) used by the template to draw icons:
                'Nutrition Flag':     'Yes' if flags.get('nutrition') else 'No',
                'Focus Case Flag':    'Yes' if flags.get('focus') else 'No',
                # Optional alternates if you ever want booleans in templates:
                'nutrition_flag':     flags.get('nutrition'),
                'focus_flag':         flags.get('focus'),
            })
        error = None
    except Exception as e:
        current_app.logger.error(f"Error loading clients for charts: {e}")
        columns, data, error = [], [], "Could not load client list."

    return render_template(
        'charts/charts.html',
        columns=columns,
        data=data,
        error=error,
        active_page='charts',
        filter_status=filter_status,
        filter_applied=filter_applied,
        filter_client=filter_client
    )

# ------------------------------------------------------------------
# Per-client chart partial
# ------------------------------------------------------------------
@charts_bp.route('/client/<client>', methods=['GET'])
def client_chart(client):
    """
    Render the client's chart form using DB entries only.
    """
    # Fetch the client object once (handy if templates want status, email, etc.)
    client_obj = Client.query.filter_by(name=client).first()
    client_status = (client_obj.status if client_obj and client_obj.status else '').strip()

    sheets = {}
    for tab in EXPECTED_TABS:
        try:
            entries = (
                ChartEntry.query
                          .filter_by(client_name=client, sheet=tab)
                          .order_by(ChartEntry.created_at)
                          .all()
            )
        except Exception as e:
            current_app.logger.error(f"[client_chart] Query error for {client}/{tab}: {e}")
            entries = []

        if entries:
            data = [e.data for e in entries]
        else:
            data = DEFAULT_ROWS.get(tab, [])

        # The templates only need .data; they don’t rely on .columns anymore
        sheets[tab] = {'data': data}

    return render_template(
        'charts/_client_form.html',
        client=client,
        client_status=client_status,   # expose selected client's status to the partial
        sheets=sheets
    )

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _rows_from_sheet_obj(sheet_obj):
    """
    Accept either {'data': [...]} or just a list of rows.
    Return a list or None if invalid.
    """
    if isinstance(sheet_obj, dict) and isinstance(sheet_obj.get('data'), list):
        return sheet_obj['data']
    if isinstance(sheet_obj, list):
        return sheet_obj
    return None

def _is_m_block_field(val: str) -> bool:
    """True if Field starts with M0:/M2:/M3: (the autosaved blocks)."""
    if not isinstance(val, str):
        return False
    return val.startswith('M0:') or val.startswith('M2:') or val.startswith('M3:')

# ------------------------------------------------------------------
# Save: DB-only
# ------------------------------------------------------------------
@charts_bp.route('/client/<client>/save', methods=['POST'])
def save_client_chart(client):
    """
    Save data into DB.

    Accepts either:
      1) { "section": "<sheet>", "data": [...] }                ← used by autosave
         - For section == "measures": PARTIAL replace of only M0:/M2:/M3: rows
         - For others: full sheet replace

      2) { "sheets": { "<sheet>": {"data":[...]}, ... } }      ← bulk replace / merge
         or   { "<sheet>": {"data":[...]}, ... }               ← bulk replace / merge
    """
    raw = request.get_data(as_text=True)
    current_app.logger.info(f"[save_client_chart] RAW data for {client}: {raw!r}")

    # Parse JSON
    try:
        payload = request.get_json(force=True) or {}
    except Exception as e:
        current_app.logger.error(f"[save_client_chart] JSON parse error for {client}: {e}")
        return jsonify(status='error', message='Invalid JSON'), 400

    # ------------------------------------------------------------
    # Mode 1: {section, data} — single-sheet save (supports partial)
    # ------------------------------------------------------------
    if isinstance(payload, dict) and 'section' in payload:
        section = str(payload.get('section', '')).lower().strip()
        rows = payload.get('data') or []

        if section not in EXPECTED_TABS:
            current_app.logger.warning(f"[save_client_chart] Unknown section '{section}' in payload")
            return jsonify(status='error', message=f"Unknown section '{section}'"), 400

        # Validate rows
        if not isinstance(rows, list):
            return jsonify(status='error', message='`data` must be a list'), 400

        # -- PARTIAL replace for MEASURES (only M0/M2/M3) --------------------
        if section == 'measures':
            try:
                # Delete only entries whose data.Field starts with M0:/M2:/M3:
                existing = (ChartEntry.query
                                       .filter_by(client_name=client, sheet='measures')
                                       .all())
                deleted = 0
                for ent in existing:
                    field = ''
                    try:
                        field = (ent.data or {}).get('Field', '') or ''
                    except Exception:
                        field = ''
                    if _is_m_block_field(field):
                        db.session.delete(ent)
                        deleted += 1

                # Insert ONLY incoming M-block rows (ignore accidental grid rows)
                inserted = 0
                for row in rows:
                    if isinstance(row, dict) and _is_m_block_field(row.get('Field', '')):
                        db.session.add(ChartEntry(client_name=client, sheet='measures', data=row))
                        inserted += 1
                    else:
                        current_app.logger.warning(f"[save_client_chart] Skipping non M-block row in partial measures save: {row!r}")

                db.session.commit()
                return jsonify(status='success',
                               mode='partial',
                               sheet='measures',
                               deleted=deleted,
                               inserted=inserted), 200
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"[save_client_chart] Measures partial write failed for {client}: {e}")
                return jsonify(status='error', message='Database error (measures partial)'), 500

        # -- Full replace for any other section ------------------------------
        try:
            ChartEntry.query.filter_by(client_name=client, sheet=section).delete(synchronize_session=False)
            inserted = 0
            for row in rows:
                if isinstance(row, dict):
                    db.session.add(ChartEntry(client_name=client, sheet=section, data=row))
                    inserted += 1
                else:
                    current_app.logger.warning(f"[save_client_chart] Skipping non-dict row in '{section}': {row!r}")
            db.session.commit()
            return jsonify(status='success', mode='replace', sheet=section, inserted=inserted), 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"[save_client_chart] DB error (section replace) for {client}/{section}: {e}")
            return jsonify(status='error', message='Database error'), 500

    # ------------------------------------------------------------
    # Mode 2: bulk — allow {"sheets": {...}} or direct {...}
    # ------------------------------------------------------------
    if 'sheets' in payload and isinstance(payload['sheets'], dict):
        payload = payload['sheets']

    if not isinstance(payload, dict):
        return jsonify(status='error', message='Invalid payload root'), 400

    # Normalize/parse incoming sheets
    parsed = {}
    for sheet_name, sheet_obj in payload.items():
        sheet = str(sheet_name).lower()
        if sheet not in EXPECTED_TABS:
            current_app.logger.warning(f"[save_client_chart] Ignoring unknown sheet '{sheet_name}'")
            continue

        rows = _rows_from_sheet_obj(sheet_obj)
        if rows is None:
            current_app.logger.warning(f"[save_client_chart] Invalid payload for sheet '{sheet}': {sheet_obj!r}")
            continue

        parsed[sheet] = rows

    if not parsed:
        return jsonify(status='error', message='No valid sheets to save'), 400

    try:
        total_inserted = 0
        affected_sheets = []

        for sheet, rows in parsed.items():
            if sheet == 'measures':
                # --- MERGE semantics for 'measures' in bulk:
                # Determine what the incoming rows represent
                incoming_mblock = [r for r in rows if isinstance(r, dict) and _is_m_block_field(r.get('Field', ''))]
                incoming_grid   = [r for r in rows if isinstance(r, dict) and not _is_m_block_field(r.get('Field', ''))]

                existing = (ChartEntry.query
                                       .filter_by(client_name=client, sheet='measures')
                                       .all())

                # If any grid rows are coming, delete only existing GRID rows (preserve M-blocks)
                deleted_grid = 0
                if incoming_grid:
                    for ent in existing:
                        field = (ent.data or {}).get('Field', '') or ''
                        if not _is_m_block_field(field):
                            db.session.delete(ent)
                            deleted_grid += 1

                # If any M-block rows are coming, delete existing M-block rows
                deleted_mblock = 0
                if incoming_mblock:
                    for ent in existing:
                        field = (ent.data or {}).get('Field', '') or ''
                        if _is_m_block_field(field):
                            db.session.delete(ent)
                            deleted_mblock += 1

                # Insert incoming rows (both parts if present)
                inserted = 0
                for row in rows:
                    if isinstance(row, dict):
                        db.session.add(ChartEntry(client_name=client, sheet='measures', data=row))
                        inserted += 1
                    else:
                        current_app.logger.warning(f"[save_client_chart] Skipping non-dict row in 'measures': {row!r}")

                current_app.logger.info(
                    f"[save_client_chart] measures bulk -> deleted_grid={deleted_grid}, "
                    f"deleted_mblock={deleted_mblock}, inserted={inserted}"
                )

                total_inserted += inserted
                affected_sheets.append('measures')

            else:
                # --- Full replace for other sheets
                ChartEntry.query.filter_by(client_name=client, sheet=sheet).delete(synchronize_session=False)
                inserted = 0
                for row in rows:
                    if isinstance(row, dict):
                        db.session.add(ChartEntry(client_name=client, sheet=sheet, data=row))
                        inserted += 1
                    else:
                        current_app.logger.warning(f"[save_client_chart] Skipping non-dict row in '{sheet}': {row!r}")
                total_inserted += inserted
                affected_sheets.append(sheet)

        db.session.commit()
        return jsonify(
            status='success',
            mode='bulk_merge' if 'measures' in parsed else 'bulk_replace',
            saved=total_inserted,
            sheets=affected_sheets
        ), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[save_client_chart] DB error (bulk handling) for {client}: {e}")
        return jsonify(status='error', message='Database error'), 500


# ------------------------------------------------------------------
# DEBUG: Inspect the DB URI and counts used by the running server
# ------------------------------------------------------------------
@charts_bp.route('/debug/db', methods=['GET'])
def debug_db():
    """
    GET /charts/debug/db?client=<name>

    Returns:
      - the SQLAlchemy DB URI the SERVER is using
      - total ChartEntry rows, total 'measures' rows
      - list of distinct clients
      - if client is provided: counts of M0/M2/M3 rows + a small sample
    """
    try:
        client = request.args.get('client', '')
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')

        total_rows = ChartEntry.query.count()
        meas_rows = ChartEntry.query.filter_by(sheet='measures').count()

        m0 = m2 = m3 = 0
        sample = []
        if client:
            rows = (ChartEntry.query
                    .filter_by(client_name=client, sheet='measures')
                    .order_by(ChartEntry.created_at.desc())
                    .all())
            for r in rows:
                f = (r.data or {}).get('Field', '')
                if isinstance(f, str):
                    if f.startswith('M0:'): m0 += 1
                    if f.startswith('M2:'): m2 += 1
                    if f.startswith('M3:'): m3 += 1
            for r in rows[:5]:
                d = r.data or {}
                sample.append({
                    "Field": d.get("Field"),
                    "DATE": d.get("DATE"),
                    "LB": d.get("LB"),
                    "H1": d.get("H1"),
                    "H2": d.get("H2"),
                    "TAG": d.get("TAG"),
                })

        clients = [c[0] for c in db.session.query(ChartEntry.client_name)
                   .distinct().all()]

        return jsonify(
            uri=uri,
            total=total_rows,
            measures_total=meas_rows,
            clients=clients,
            client=client,
            M0=m0, M2=m2, M3=m3,
            sample=sample
        ), 200
    except Exception as e:
        current_app.logger.error(f"[debug_db] error: {e}")
        return jsonify(error="debug_db failure", detail=str(e)), 500
