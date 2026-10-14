"""Ronda 6, punto 23 de Validacion_observaciones_RAG_STUDIO.md
(hallazgo real de usuario, video 3): "Valores por fuente" no ofrecía
ninguna forma de desasociar/quitar un valor de metadato ya guardado --
solo SetSourceMetadataValue (upsert). El nuevo caso de uso
DeleteSourceMetadataValue registra el borrado en metadata_value_change
igual que cualquier otro cambio (ver docstring de MetadataValueChange),
pero con new_value=None -- hasta ahora esa columna era NOT NULL porque
solo existía el camino "de un valor a otro valor", nunca "a sin
asignar".

SQLite no soporta ALTER COLUMN directo; se usa batch_alter_table
(recrea la tabla internamente) para relajar la restricción NOT NULL,
igual que hace Alembic con cualquier otro cambio de columna sobre
SQLite.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("metadata_value_change") as batch_op:
        batch_op.alter_column("new_value", existing_type=sa.String, nullable=True)


def downgrade() -> None:
    # Downgrade a NOT NULL requeriría antes rellenar cualquier fila con
    # new_value=None (las que dejó DeleteSourceMetadataValue) -- se
    # asume que downgrade solo se usa en desarrollo, antes de haber
    # borrado ningún valor real; si existieran, esta migración fallaría
    # de forma explícita en vez de corromper datos silenciosamente.
    with op.batch_alter_table("metadata_value_change") as batch_op:
        batch_op.alter_column("new_value", existing_type=sa.String, nullable=False)
