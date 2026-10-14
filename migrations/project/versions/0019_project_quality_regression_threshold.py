"""Ronda 53 (Propuesta de evaluación continua reforzada, opciones B'+C
confirmadas por el consultor): agrega `quality_regression_threshold` a
`project` -- el umbral de caída relativa de Recall@3/MRR, entre dos
corridas "completa" consecutivas, que la nueva compuerta de liberación
"Regresión de recuperación" usa para decidir si bloquea (ver
application/release/queries/evaluate_release_gates.py::
_retrieval_regression_gate). NULLABLE, sin default: NULL significa
"usar el valor por defecto de la instalación" (15% relativo,
DEFAULT_QUALITY_REGRESSION_THRESHOLD en application/quality/
options.py) -- todo proyecto existente queda así, sin ningún backfill,
y con el mismo comportamiento que tendría si el campo no existiera.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column("quality_regression_threshold", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project", "quality_regression_threshold")
