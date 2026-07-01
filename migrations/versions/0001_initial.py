"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "programs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("department", sa.String),
        sa.Column("duration_years", sa.Float),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
    )

    op.create_table(
        "admission_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("program_id", sa.Integer, sa.ForeignKey("programs.id"), nullable=False),
        sa.Column("allowed_streams", sa.ARRAY(sa.String), nullable=False),
        sa.Column("min_matric_pct", sa.Float, nullable=False),
        sa.Column("min_inter_pct", sa.Float, nullable=False),
        sa.Column("required_subjects", sa.ARRAY(sa.String), server_default="{}"),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("source_url", sa.String),
        sa.Column("verified_by", sa.String),
    )
    op.create_index("ix_admission_rules_program_id", "admission_rules", ["program_id"])

    op.create_table(
        "program_content",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("program_id", sa.Integer, sa.ForeignKey("programs.id"), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("curriculum", sa.Text),
        sa.Column("career_opportunities", sa.Text),
        sa.Column("required_skills", sa.ARRAY(sa.String), server_default="{}"),
        sa.Column("interest_tags", sa.ARRAY(sa.String), server_default="{}"),
        sa.Column("career_keywords", sa.ARRAY(sa.String), server_default="{}"),
    )

    op.create_table(
        "recommendation_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_hash", sa.String, index=True),
        sa.Column("input_profile", sa.JSON),
        sa.Column("eligible_program_ids", sa.ARRAY(sa.Integer)),
        sa.Column("ranked_program_ids", sa.ARRAY(sa.Integer)),
        sa.Column("rule_version_ids", sa.ARRAY(sa.Integer)),
        sa.Column("model_version", sa.String),
        sa.Column("llm_output", sa.JSON, nullable=True),
        sa.Column("created_at", sa.String),
    )


def downgrade():
    op.drop_table("recommendation_log")
    op.drop_table("program_content")
    op.drop_table("admission_rules")
    op.drop_table("programs")
