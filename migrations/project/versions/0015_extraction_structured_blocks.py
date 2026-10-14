"""Pista B.2 del ADR-003 (docs proyecto/RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx,
sección 3.1): bloques de contenido estructurado identificados por la
extracción (hoy, hojas XLSX o el CSV completo), ADEMÁS del texto que ya
se guardaba -- nunca en vez de él.

Añade a `extraction_record` y `extraction_record_history`:
- `structured_blocks` (NULLABLE, sin default): dict serializado en JSON
  (ver ExtractionRecord.structured_blocks). NULL significa "sin bloques
  estructurados" -- el estado real de toda fila existente (creada antes
  de esta migración) y de cualquier fuente que no sea XLSX/CSV; el
  repositorio lo trata como "{}" al leer, sin backfill automático
  (mismo criterio ya usado para parent_chunk_id/structured_content en
  la migración 0014).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("extraction_record", sa.Column("structured_blocks", sa.Text(), nullable=True))
    op.add_column("extraction_record_history", sa.Column("structured_blocks", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("extraction_record_history", "structured_blocks")
    op.drop_column("extraction_record", "structured_blocks")
