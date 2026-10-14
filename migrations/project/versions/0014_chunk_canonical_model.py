"""Pista B.1 del ADR-003 (docs proyecto/RAG_STUDIO_ADR-003_Evolucion_Capa_Canonica.docx,
"Plan de fases"; diseño detallado en
docs proyecto/RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 4):
modelo canónico de Chunk, primer paso (B.1a) -- solo esquema, sin que
ninguna estrategia de fragmentación use los campos nuevos todavía.

Añade a `chunk`:
- `parent_chunk_id` (NULLABLE, sin default): id de un chunk
  chunk_type="padre" que agrupa a este fragmento junto con sus
  hermanos. NULL significa "sin padre" -- el mismo estado, implícito,
  que tenía todo chunk antes de esta migración; ningún esquema
  existente cambia de comportamiento. Sin FK real, mismo criterio ya
  usado por `previous_chunk_id`/`next_chunk_id`.
- `structured_content` (NULLABLE, sin default): contenido estructurado
  del fragmento (dict serializado en JSON), sin aplanar a texto
  Markdown. NULL significa "sin contenido estructurado" -- el estado
  real de todo chunk existente. Ningún extractor ni divisor lo puebla
  todavía (eso es trabajo de la Pista B.2); se agrega la columna ahora
  para no repetir esta migración cuando B.2 empiece.

El tercer campo de la Pista B.1 (`element_type`) no exige ninguna
migración: se resolvió reutilizando el Enum `ChunkType` ya existente
(agregando los valores "encabezado" y "padre" del lado de Python,
domain/ingestion/entities.py) en vez de agregar una columna paralela
-- la columna `chunk_type` ya es `sa.String` en este esquema, así que
un valor nuevo del Enum no requiere ALTER de columna ni backfill.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunk", sa.Column("parent_chunk_id", sa.String(), nullable=True))
    op.add_column("chunk", sa.Column("structured_content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunk", "structured_content")
    op.drop_column("chunk", "parent_chunk_id")
