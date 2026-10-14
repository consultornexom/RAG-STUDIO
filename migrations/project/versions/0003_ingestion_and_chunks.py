"""Etapa 3: ingesta (extracción y fragmentación de fuentes).

Añade: extraction_record, chunk, fragmentation_policy.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_record",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("source_id", sa.String, nullable=False, unique=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page_breaks", sa.String, nullable=False, server_default="[]"),
        sa.Column("extraction_method", sa.String, nullable=False, server_default=""),
        sa.Column("warnings", sa.String, nullable=False, server_default="[]"),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extraction_record_project_id", "extraction_record", ["project_id"])

    op.create_table(
        "chunk",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("section_title", sa.String, nullable=True),
        sa.Column("page_start", sa.Integer, nullable=True),
        sa.Column("page_end", sa.Integer, nullable=True),
        sa.Column("chunk_type", sa.String, nullable=False),
        sa.Column("previous_chunk_id", sa.String, nullable=True),
        sa.Column("next_chunk_id", sa.String, nullable=True),
        sa.Column("semantic_summary", sa.String, nullable=True),
        sa.Column("inherited_metadata", sa.String, nullable=False, server_default="{}"),
        sa.Column("pipeline_version", sa.String, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chunk_project_id", "chunk", ["project_id"])
    op.create_index("ix_chunk_source_id", "chunk", ["source_id"])

    op.create_table(
        "fragmentation_policy",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("document_type_code", sa.String, nullable=False),
        sa.Column("strategy", sa.String, nullable=False),
        sa.Column("target_tokens", sa.Integer, nullable=False, server_default="500"),
        sa.Column("overlap_tokens", sa.Integer, nullable=False, server_default="60"),
        sa.Column("min_tokens", sa.Integer, nullable=False, server_default="80"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "document_type_code", name="uq_fragmentation_policy_code"),
    )
    op.create_index("ix_fragmentation_policy_project_id", "fragmentation_policy", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_fragmentation_policy_project_id", table_name="fragmentation_policy")
    op.drop_table("fragmentation_policy")
    op.drop_index("ix_chunk_source_id", table_name="chunk")
    op.drop_index("ix_chunk_project_id", table_name="chunk")
    op.drop_table("chunk")
    op.drop_index("ix_extraction_record_project_id", table_name="extraction_record")
    op.drop_table("extraction_record")
