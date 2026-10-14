"""Ítem 4 de la evaluación de madurez post-8-etapas: copiar el archivo
original al registrar una fuente.

Añade la columna `original_copy_path` a `source` -- ruta (dentro de
sources/original/ del proyecto) de la copia local del archivo, cuando
se pudo copiar al registrar la fuente (o al corregir su ubicación
mientras siga sin bloquear). Nullable y sin default: los registros
existentes quedan en NULL, que es exactamente el mismo significado que
tenía el comportamiento de siempre (extracción leyendo de `location`
directamente) -- ningún backfill es necesario ni posible (no hay forma
de reconstruir retroactivamente una copia que nunca se hizo).

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source", sa.Column("original_copy_path", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("source", "original_copy_path")
