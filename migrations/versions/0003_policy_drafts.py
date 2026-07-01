"""add policy_drafts table

Revision ID: 0003_policy_drafts
Revises: 0002_preferred_stream
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_policy_drafts"
down_revision = "0002_preferred_stream"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "policy_drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("program_id", sa.Integer, nullable=True),
        sa.Column("source_url", sa.String, nullable=False),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("scraped_data", sa.JSON, nullable=False),
        sa.Column("diff_summary", sa.Text, nullable=False),
        sa.Column("diff_detail", sa.JSON, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String, nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("created_rule_id", sa.Integer, nullable=True),
    )
    op.create_index("ix_policy_drafts_status", "policy_drafts", ["status"])
    op.create_index("ix_policy_drafts_program_id", "policy_drafts", ["program_id"])


def downgrade():
    op.drop_index("ix_policy_drafts_program_id", table_name="policy_drafts")
    op.drop_index("ix_policy_drafts_status", table_name="policy_drafts")
    op.drop_table("policy_drafts")
