"""add preferred_stream to programs

Revision ID: 0002_preferred_stream
Revises: 0001_initial
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_preferred_stream"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("programs", sa.Column("preferred_stream", sa.String, nullable=True))


def downgrade():
    op.drop_column("programs", "preferred_stream")
