"""Pista B.4 del ADR-003 (enrutamiento multi-índice determinista, docs
proyecto/RAG_STUDIO_Propuesta_B4_Enrutamiento_Multiindice.docx):

Añade a `intent`:
- `resolution_mode` (NOT NULL, default 'semantico'): ver
  domain.conversational.entities.IntentResolutionMode. Toda intención
  creada antes de esta migración recibe 'semantico' -- exactamente el
  comportamiento de siempre (vector+BM25, nunca la vía estructurada de
  la Pista B.2), sin que nadie tenga que reclasificarla a mano.

Añade a `conversational_variable`:
- `structured_column` (NULLABLE, sin default): ver
  domain.conversational.entities.ConversationalVariable.
  structured_column. NULL significa "sin columna estructurada ligada"
  -- el estado real de toda variable existente, mismo criterio que
  `metadata_field_id` (NULLABLE desde su migración original).

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intent",
        sa.Column("resolution_mode", sa.String(), nullable=False, server_default="semantico"),
    )
    op.add_column("conversational_variable", sa.Column("structured_column", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversational_variable", "structured_column")
    op.drop_column("intent", "resolution_mode")
