"""Ronda 100 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
agrega `chunk.section_path`, la ruta de encabezados Markdown que rige a cada
fragmento producido por la estrategia por_encabezado (lista JSON de
{"level", "title"}).

NULLABLE, sin default y sin backfill: los fragmentos ya guardados quedan con
NULL (ruta vacía) y la búsqueda se comporta con ellos exactamente como antes.
La ruta se completa al volver a fragmentar la fuente; el pipeline de la Ronda
98 lo hace solo para las fuentes con política por_encabezado (cambia la
versión del fragmentador en su huella de política), sin reconstruir el resto.

`text` no cambia: la ruta es un dato aparte.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunk", sa.Column("section_path", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chunk") as batch:
        batch.drop_column("section_path")
