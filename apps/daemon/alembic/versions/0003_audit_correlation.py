"""audit correlation id

Revision ID: 0003_correlation
Revises: 0002_permissions
Create Date: 2026-07-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_correlation"
down_revision: str | None = "0002_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("correlation_id", sa.String(length=36), nullable=False, server_default=""),
    )
    op.create_index(
        op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_correlation_id"), table_name="audit_events")
    op.drop_column("audit_events", "correlation_id")
