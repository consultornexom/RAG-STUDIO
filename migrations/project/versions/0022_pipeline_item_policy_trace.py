"""Ronda 98 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
trazabilidad de la política de fragmentación y causa de la decisión en
cada fuente de una corrida del pipeline.

Agrega a `pipeline_run_item`, todas NULLABLE, sin default y sin backfill:
- `document_type_code`: tipo documental de la fuente al procesarla;
- `policy_document_type_code`, `policy_origin`, `policy_strategy`: qué
  política de fragmentación se aplicó y de dónde salió;
- `policy_hash`, `metadata_hash`, `chunks_digest`: huellas que usa la
  incrementalidad, además del hash del archivo (`content_hash`);
- `reason`: por qué se procesó u omitió la fuente.

Las filas existentes quedan con NULL: RunPipeline trata una corrida
anterior sin huellas como "configuración desconocida" y reprocesa la
fuente una vez (motivo explícito en el reporte), en vez de omitirla con
una política que quizá no corresponde a su tipo documental.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_COLUMNAS = (
    ("document_type_code", sa.String),
    ("policy_document_type_code", sa.String),
    ("policy_origin", sa.String),
    ("policy_strategy", sa.String),
    ("policy_hash", sa.String),
    ("metadata_hash", sa.String),
    ("chunks_digest", sa.String),
    ("reason", sa.Text),
)


def upgrade() -> None:
    for nombre, tipo in _COLUMNAS:
        op.add_column("pipeline_run_item", sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pipeline_run_item") as batch:
        for nombre, _ in reversed(_COLUMNAS):
            batch.drop_column(nombre)
