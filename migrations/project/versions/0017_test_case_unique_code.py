"""Auditoría Ronda 48 (pruebas reales con documentos de Licenciatura/),
hallazgo menor #162 (Validacion_observaciones_RAG_STUDIO.md, Ronda 48 y
Ronda 51): agrega un índice único sobre (project_id, code) en
`test_case`, que hasta ahora no tenía ninguna restricción de unicidad
-- a diferencia de `channeling_scheme` (uq_channeling_scheme_code,
migración 0006), que sí la tenía desde su creación. Se podían crear dos
casos de prueba con el mismo `code` (p. ej. dos "UDL-001" distintos)
sin ningún error, lo que vuelve ambiguo un reporte de evaluación (que
identifica cada resultado por `test_case_code`).

Se usa `op.create_index(..., unique=True)` en vez de
`op.create_unique_constraint` porque la tabla ya existe con datos
reales en instalaciones existentes, y SQLite no soporta agregar una
restricción con ALTER TABLE sin recrear la tabla completa (modo
"batch" de Alembic) -- un índice único aditivo ofrece la misma
protección real sin ese riesgo. Si una instalación ya tuviera dos casos
de prueba con el mismo (project_id, code) -- ningún caso conocido hoy,
verificado contra el proyecto real "AGENTE UDL" (0 filas en
`test_case`) --, esta migración fallaría de forma visible en vez de
aplicarse a medias; ese caso debe resolverse a mano (renombrando uno de
los dos códigos) antes de reintentarla.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-20
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_test_case_code", "test_case", ["project_id", "code"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_test_case_code", table_name="test_case")
