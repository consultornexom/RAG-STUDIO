"""Etapa 7: liberación (compuertas, dictamen, entregables).

Añade: release_record. Conserva historial completo (igual que
pipeline_run/evaluation_run) -- una liberación bloqueada o rechazada
queda como evidencia de que se intentó y por qué no procedió.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_record",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("checklist", sa.Text, nullable=False, server_default="{}"),
        sa.Column("dictamen", sa.Text, nullable=False, server_default=""),
        sa.Column("evidence", sa.Text, nullable=False, server_default="{}"),
        sa.Column("deliverables_report", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_release_record_project_id", "release_record", ["project_id"])
    op.create_index("ix_release_record_status", "release_record", ["status"])


def downgrade() -> None:
    op.drop_index("ix_release_record_status", table_name="release_record")
    op.drop_index("ix_release_record_project_id", table_name="release_record")
    op.drop_table("release_record")
