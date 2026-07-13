"""audit hash chain

Revision ID: 0004_hash_chain
Revises: 0003_correlation
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_hash_chain"
down_revision: str | None = "0003_correlation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("prev_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "audit_events",
        sa.Column("hash", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("audit_events", "hash")
    op.drop_column("audit_events", "prev_hash")
