# test_api.py
from datetime import datetime, timedelta
import pandas as pd
from app.figurella_reports.services.figurella_api import sync_customers_to_supabase, _fetch_customers_iter

# ───────────────────────────────────────────────
# 📆 Dynamic 6-month window (past + future)
today = datetime.now()
frm   = today - timedelta(days=90)
to    = today + timedelta(days=90)

EXPORT_XLSX = True
OUTPUT_PATH = f"customers_{frm.date()}_to_{to.date()}.xlsx"
# ───────────────────────────────────────────────

print(f"🗓  Syncing Customers from {frm.isoformat()} to {to.isoformat()}")

# 🔁 1. Sync into Supabase
result = sync_customers_to_supabase(frm)
print("✅ Sync to Supabase complete:")
for k, v in result.items():
    print(f"  {k}: {v}")

# 📤 2. Export to Excel
if EXPORT_XLSX:
    print(f"\n📤 Exporting to Excel: {OUTPUT_PATH}")
    rows = list(_fetch_customers_iter(frm))

    def within_range(r):
        dt = r.get("lastAppointmentDate") or r.get("registrationDate")
        if not dt: return True
        try:
            d = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
            return frm <= d <= to
        except: return False

    filtered = [r for r in rows if within_range(r)]
    if filtered:
        df = pd.DataFrame(filtered)
        with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="All")
            if "status" in df.columns:
                df.groupby("status").size().reset_index(name="count")\
                  .sort_values("count", ascending=False)\
                  .to_excel(writer, index=False, sheet_name="Summary")
        print(f"✅ Exported {len(filtered)} rows to {OUTPUT_PATH}")
    else:
        print("⚠️ No data found for this window. Nothing exported.")
