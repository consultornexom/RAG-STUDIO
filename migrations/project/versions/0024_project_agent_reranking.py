"""Ronda 102 (C4, autorizado por NEXOM): agrega `agent_reranking` a
`project` -- ajuste "Reranking en el agente" del Simulador y del canal de
mensajes. NULLABLE, sin default: NULL significa "automático" (se aplica el
reranking si la instalación tiene modelo), exactamente el comportamiento
anterior a esta migración; ningún proyecto existente necesita backfill.
No toca documentos, fragmentos ni metadatos.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project", sa.Column("agent_reranking", sa.Boolean, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.drop_column("agent_reranking")
