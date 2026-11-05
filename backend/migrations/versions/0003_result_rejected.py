"""search results hidden by visual verification

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05 11:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_results", sa.Column("is_rejected", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("search_results", "is_rejected")
