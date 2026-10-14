"""ADR-002 (docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx),
Fase 1: publicar una instantánea de solo lectura del estado de un
proyecto (project.db + índice Qdrant), separada de projects/<project_id>
donde la app de escritorio sigue editando en vivo -- para que un futuro
runtime de producción pueda leer un estado certificado sin competir
por el lock exclusivo que Qdrant toma sobre su directorio de índice
mientras está abierto.

Añade: project_snapshot. Conserva historial completo, mismo criterio
que release_record/pipeline_run -- cada publicación es una fila nueva.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_snapshot",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source_release_id", sa.String, nullable=True),
        sa.Column("snapshot_dir", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_snapshot_project_id", "project_snapshot", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_snapshot_project_id", table_name="project_snapshot")
    op.drop_table("project_snapshot")
