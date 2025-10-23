"""guarded add: completed/completed_at/rrule/exdates (idempotent)"""

from alembic import op
import sqlalchemy as sa

# Alembic identifiers
revision = "27312b64a3f5"
down_revision = "9e5ee5184742"  # keep your actual previous rev here
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return any(col["name"] == column for col in insp.get_columns(table))


def upgrade():
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("events") as batch:
        # completed
        if not _has_column("events", "completed"):
            batch.add_column(sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
            batch.alter_column("completed", server_default=None)

        # completed_at
        if not _has_column("events", "completed_at"):
            batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

        # rrule (JSON; on SQLite this will map to TEXT)
        if not _has_column("events", "rrule"):
            batch.add_column(sa.Column("rrule", sa.JSON(), nullable=True))

        # exdates (JSON list). Provide a literal default for SQLite, then drop it.
        if not _has_column("events", "exdates"):
            batch.add_column(sa.Column("exdates", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
            batch.alter_column("exdates", server_default=None)


def downgrade():
    with op.batch_alter_table("events") as batch:
        if _has_column("events", "exdates"):
            batch.drop_column("exdates")
        if _has_column("events", "rrule"):
            batch.drop_column("rrule")
        if _has_column("events", "completed_at"):
            batch.drop_column("completed_at")
        if _has_column("events", "completed"):
            batch.drop_column("completed")
