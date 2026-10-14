"""Etapa 4 (nucleo RAG): estado del indice vectorial por proyecto.

Añade: index_info. El contenido vectorial en si (embeddings) no vive
en SQLite -- vive en el directorio Qdrant local
(InstallationPaths.qdrant_index_dir), fuera del alcance de Alembic;
esta tabla solo guarda que modelo se uso y cuantos puntos tiene, para
poder detectar inconsistencias (p. ej. cambiar de modelo de
embeddings sin reindexar) sin tener que abrir Qdrant.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "index_info",
        sa.Column("project_id", sa.String, primary_key=True),
        sa.Column("embedding_provider", sa.String, nullable=False),
        sa.Column("embedding_model", sa.String, nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("points_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("index_info")
