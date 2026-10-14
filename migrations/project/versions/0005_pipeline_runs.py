"""Etapa 3: pipeline reproducible (corrida por lote sobre todas las
fuentes de un proyecto).

Añade: pipeline_run, pipeline_run_item. A diferencia de la mayoría de
las tablas de este proyecto (upsert, solo el estado vigente), estas dos
conservan el historial completo de corridas -- el documento maestro
exige poder auditar corridas pasadas, no solo la última.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_run",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("document_type_code", sa.String, nullable=False, server_default="default"),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pipeline_run_project_id", "pipeline_run", ["project_id"])

    op.create_table(
        "pipeline_run_item",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, nullable=False),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("source_title", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=True),
        sa.Column("steps_completed", sa.String, nullable=False, server_default="[]"),
        sa.Column("chunks_indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("warnings", sa.String, nullable=False, server_default="[]"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pipeline_run_item_run_id", "pipeline_run_item", ["run_id"])
    op.create_index("ix_pipeline_run_item_project_id", "pipeline_run_item", ["project_id"])
    op.create_index("ix_pipeline_run_item_source_id", "pipeline_run_item", ["source_id"])
    op.create_index("ix_pipeline_run_item_status", "pipeline_run_item", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_run_item_status", table_name="pipeline_run_item")
    op.drop_index("ix_pipeline_run_item_source_id", table_name="pipeline_run_item")
    op.drop_index("ix_pipeline_run_item_project_id", table_name="pipeline_run_item")
    op.drop_index("ix_pipeline_run_item_run_id", table_name="pipeline_run_item")
    op.drop_table("pipeline_run_item")
    op.drop_index("ix_pipeline_run_project_id", table_name="pipeline_run")
    op.drop_table("pipeline_run")
