"""permissions and workspaces

Revision ID: 0002_permissions
Revises: 481eb5e99a59
Create Date: 2026-07-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_permissions"
down_revision: str | None = "481eb5e99a59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("trusted", sa.Boolean(), nullable=False),
        sa.Column("approved_domains_json", sa.JSON(), nullable=False),
        sa.Column("approved_apps_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "permission_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_permission_grants_workspace_id"),
        "permission_grants",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_permission_grants_workspace_id"), table_name="permission_grants")
    op.drop_table("permission_grants")
    op.drop_table("workspace_profiles")
