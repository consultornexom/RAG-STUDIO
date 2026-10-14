"""Ronda 53 (Propuesta de evaluación continua reforzada, ver Validacion_
observaciones_RAG_STUDIO.md, Ronda 53): corrige una brecha real de
persistencia detectada al diseñar las opciones B'/C -- `domain/quality/
entities.py::EvaluationResultItem.retrieval_check_applicable` y
`.expected_source_rank` existen desde la Pista A.1 (ADR-003) y ya los
usa `EvaluationRun.recall_at_k()`, pero `EvaluationResultItemRecord`
nunca tuvo columnas para ellos: `save()` no los escribía y
`_record_to_item()` no los reconstruía al leer. El único lugar donde
sobrevivían era el objeto en memoria que devuelve
`RunEvaluation.execute()` justo al terminar una corrida -- cualquier
corrida releída de la base de datos (todo el historial, incluida la que
usan las opciones B'/C para comparar contra una corrida de referencia)
perdía ambos campos y `recall_at_k()`/`mean_reciprocal_rank()` volvían
`None` sin ninguna razón real para ello.

`retrieval_check_applicable`: NOT NULL, default `false` -- toda fila ya
existente queda como "no se evaluó recuperación en este caso", que es
exactamente el estado (incorrecto para casos que sí declaraban una
fuente esperada, pero indistinguible hoy) que ya tenían de hecho antes
de esta migración; no hay manera de recuperar retroactivamente cuál
caso sí aplicaba sin volver a correr la evaluación.
`expected_source_rank`: NULLABLE, sin default -- mismo criterio.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_result_item",
        sa.Column("retrieval_check_applicable", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "evaluation_result_item",
        sa.Column("expected_source_rank", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_result_item", "expected_source_rank")
    op.drop_column("evaluation_result_item", "retrieval_check_applicable")
