"""Etapa 6: calidad (banco de pruebas, corridas de evaluación,
resultados por caso).

Añade: test_case, evaluation_run, evaluation_result_item. test_case es
upsert por id (igual que la mayoría de las tablas de configuración);
evaluation_run/evaluation_result_item conservan historial completo
(igual que pipeline_run/pipeline_run_item) -- el documento maestro
exige comparar corridas pasadas (regresión), no solo la última.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_case",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("provided_variables", sa.String, nullable=False, server_default="{}"),
        sa.Column("source_id", sa.String, nullable=True),
        sa.Column("expected_intent", sa.String, nullable=True),
        sa.Column("expected_missing_variable", sa.String, nullable=True),
        sa.Column("expected_action", sa.String, nullable=True),
        sa.Column("forbidden_action", sa.String, nullable=True),
        sa.Column("expected_channeling", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("expected_source_id", sa.String, nullable=True),
        sa.Column("severity", sa.String, nullable=False, server_default="media"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_case_project_id", "test_case", ["project_id"])
    op.create_index("ix_test_case_category", "test_case", ["category"])

    op.create_table(
        "evaluation_run",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("scope", sa.String, nullable=False, server_default="completa"),
        sa.Column("category_filter", sa.String, nullable=True),
        sa.Column("test_case_id_filter", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_evaluation_run_project_id", "evaluation_run", ["project_id"])

    op.create_table(
        "evaluation_result_item",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, nullable=False),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("test_case_id", sa.String, nullable=False),
        sa.Column("test_case_code", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("verdict", sa.String, nullable=False),
        sa.Column("actual_intent", sa.String, nullable=True),
        sa.Column("actual_action", sa.String, nullable=True),
        sa.Column("actual_channeling_code", sa.String, nullable=True),
        sa.Column("mismatches", sa.String, nullable=False, server_default="[]"),
        sa.Column("regressed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_evaluation_result_item_run_id", "evaluation_result_item", ["run_id"])
    op.create_index("ix_evaluation_result_item_project_id", "evaluation_result_item", ["project_id"])
    op.create_index("ix_evaluation_result_item_test_case_id", "evaluation_result_item", ["test_case_id"])
    op.create_index("ix_evaluation_result_item_verdict", "evaluation_result_item", ["verdict"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_result_item_verdict", table_name="evaluation_result_item")
    op.drop_index("ix_evaluation_result_item_test_case_id", table_name="evaluation_result_item")
    op.drop_index("ix_evaluation_result_item_project_id", table_name="evaluation_result_item")
    op.drop_index("ix_evaluation_result_item_run_id", table_name="evaluation_result_item")
    op.drop_table("evaluation_result_item")
    op.drop_index("ix_evaluation_run_project_id", table_name="evaluation_run")
    op.drop_table("evaluation_run")
    op.drop_index("ix_test_case_category", table_name="test_case")
    op.drop_index("ix_test_case_project_id", table_name="test_case")
    op.drop_table("test_case")
