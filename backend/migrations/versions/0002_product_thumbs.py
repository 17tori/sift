"""product thumbnails cached in storage

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("thumb_key", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("thumb_src", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "thumb_src")
    op.drop_column("products", "thumb_key")
