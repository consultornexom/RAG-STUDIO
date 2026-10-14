"""Ronda 68 (corrección de un defecto real de la Fase 2/Ronda 65, no
parte del trabajo de migraciones planeado para la Fase 5): agrega
`image_relative_path` a `chunk` -- el campo del dominio (domain.
ingestion.entities.Chunk.image_relative_path, ver ese módulo) que
IndexImageSource puebla para todo Chunk tipo IMAGEN desde la Fase 3,
pero que nunca se conectó a SqlAlchemyChunkRepository/ChunkRecord: se
guardaba y se leía sin problema contra el doble en memoria de las
pruebas (InMemoryChunkRepository, que conserva el dataclass completo),
pero contra la base de datos real quedaba en None en cuanto la fila se
releía -- descubierto al escribir la prueba de integración del segundo
vacío de Fase 3 (image_results en POST /messages, ver
tests/integration/test_runtime_api.py). Sin esta columna, tanto la
pestaña de Fragmentación (Ronda 67) como el nuevo campo image_results
(Ronda 68) mostrarían siempre una ruta vacía para cualquier imagen
indexada a través del pipeline real.

NULLABLE, sin default y sin backfill: todo Chunk existente (todos de
tipo distinto de IMAGEN, porque esta funcionalidad nunca llegó a
persistir nada usable) queda con NULL, exactamente el mismo valor que
ya devolvía _record_to_chunk antes de esta migración -- no hay ningún
comportamiento previo que preservar para chunks tipo IMAGEN ya
guardados, porque nunca hubo ninguno funcional.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunk",
        sa.Column("image_relative_path", sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunk", "image_relative_path")
