"""Add completed_on to Event

Revision ID: 87f5e5e4abb2
Revises: 27312b64a3f5
Create Date: 2025-09-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '87f5e5e4abb2'
down_revision = '27312b64a3f5'
branch_labels = None
depends_on = None


def _json_with_sqlite_fallback():
    # JSON type for Postgres/MySQL; TEXT on SQLite
    return sa.JSON().with_variant(sa.Text(), 'sqlite')


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Use batch mode so SQLite can rewrite the table safely
    with op.batch_alter_table('events', schema=None) as batch_op:
        # 1) Add column as NULLABLE with a SERVER DEFAULT of empty list
        #    (so existing rows can be copied)
        batch_op.add_column(
            sa.Column(
                'completed_on',
                _json_with_sqlite_fallback(),
                nullable=True,
                server_default='[]'
            )
        )

        # If Alembic also detected a type change for exdates, keep it here.
        # (This is harmless if it's already JSON)
        try:
            batch_op.alter_column(
                'exdates',
                type_=_json_with_sqlite_fallback(),
                existing_nullable=True
            )
        except Exception:
            # Ignore if not needed
            pass

    # 2) Backfill NULLs → empty list (JSON/text form per dialect)
    if dialect == 'postgresql':
        op.execute("UPDATE events SET completed_on = '[]'::jsonb WHERE completed_on IS NULL")
    else:
        # sqlite / mysql
        op.execute("UPDATE events SET completed_on = '[]' WHERE completed_on IS NULL")

    # 3) Drop server default and enforce NOT NULL
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.alter_column('completed_on', server_default=None, nullable=False)


def downgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('completed_on')
