from run import app
from app import db
import sqlalchemy as sa

with app.app_context():
    rid = db.session.execute(
        sa.text("SELECT id FROM reports WHERE name='customer_acquisitions'")
    ).scalar()
    if rid:
        db.session.execute(sa.text(f"DELETE FROM report_history WHERE report_id={rid}"))
        db.session.commit()
        print(f"Cleared CA history for report_id={rid}")
    else:
        print("No report_id found for customer_acquisitions")
