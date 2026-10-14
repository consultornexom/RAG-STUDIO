"""Ítem 5 de la evaluación de madurez post-8-etapas: historial de
cambios en metadatos y extracciones.

Añade dos tablas de solo inserción (append-only, nunca se actualizan
ni se borran filas): metadata_value_change y
extraction_record_history. `source_metadata_value` y
`extraction_record` siguen siendo upsert (solo el valor/extracción
vigente) -- estas tablas nuevas son el historial de auditoría que
faltaba, no un reemplazo.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metadata_value_change",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("field_id", sa.String, nullable=False),
        sa.Column("previous_value", sa.String, nullable=True),
        sa.Column("new_value", sa.String, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_metadata_value_change_source_id", "metadata_value_change", ["source_id"])
    op.create_index("ix_metadata_value_change_field_id", "metadata_value_change", ["field_id"])

    op.create_table(
        "extraction_record_history",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page_breaks", sa.String, nullable=False, server_default="[]"),
        sa.Column("extraction_method", sa.String, nullable=False, server_default=""),
        sa.Column("warnings", sa.String, nullable=False, server_default="[]"),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extraction_record_history_project_id", "extraction_record_history", ["project_id"])
    op.create_index("ix_extraction_record_history_source_id", "extraction_record_history", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_extraction_record_history_source_id", table_name="extraction_record_history")
    op.drop_index("ix_extraction_record_history_project_id", table_name="extraction_record_history")
    op.drop_table("extraction_record_history")
    op.drop_index("ix_metadata_value_change_field_id", table_name="metadata_value_change")
    op.drop_index("ix_metadata_value_change_source_id", table_name="metadata_value_change")
    op.drop_table("metadata_value_change")
