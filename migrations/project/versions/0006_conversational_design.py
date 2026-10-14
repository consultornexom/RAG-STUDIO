"""Etapa 5: diseño conversacional (intenciones, variables
conversacionales, guardrails, esquemas de canalización).

Añade: intent, conversational_variable, guardrail_rule,
channeling_scheme. Las cuatro son upsert por id (o por código para
conversational_variable/channeling_scheme) -- guardan solo la versión
vigente, igual que la mayoría de las tablas de configuración de este
proyecto (a diferencia de pipeline_run/pipeline_run_item, que sí
conservan historial completo).

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intent",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("positive_examples", sa.String, nullable=False, server_default="[]"),
        sa.Column("negative_examples", sa.String, nullable=False, server_default="[]"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String, nullable=False, server_default="bajo"),
        sa.Column("required_variables", sa.String, nullable=False, server_default="[]"),
        sa.Column("optional_variables", sa.String, nullable=False, server_default="[]"),
        sa.Column("clarifying_questions", sa.String, nullable=False, server_default="{}"),
        sa.Column("response_rule", sa.Text, nullable=False, server_default=""),
        sa.Column("fallback_channeling_code", sa.String, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_intent_project_id", "intent", ["project_id"])

    op.create_table(
        "conversational_variable",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("metadata_field_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "code", name="uq_conversational_variable_code"),
    )
    op.create_index("ix_conversational_variable_project_id", "conversational_variable", ["project_id"])

    op.create_table(
        "guardrail_rule",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("rule_type", sa.String, nullable=False),
        sa.Column("conditions", sa.String, nullable=False, server_default="[]"),
        sa.Column("action", sa.String, nullable=False, server_default="responder"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_guardrail_rule_project_id", "guardrail_rule", ["project_id"])

    op.create_table(
        "channeling_scheme",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("condition", sa.Text, nullable=False, server_default=""),
        sa.Column("target_area", sa.String, nullable=False, server_default=""),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("required_data", sa.String, nullable=False, server_default="[]"),
        sa.Column("allowed_data", sa.String, nullable=False, server_default="[]"),
        sa.Column("forbidden_data", sa.String, nullable=False, server_default="[]"),
        sa.Column("summary_template", sa.Text, nullable=False, server_default=""),
        sa.Column("medium", sa.String, nullable=False, server_default="registro_manual"),
        sa.Column("user_message", sa.Text, nullable=False, server_default=""),
        sa.Column("alternative_action", sa.Text, nullable=False, server_default=""),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "code", name="uq_channeling_scheme_code"),
    )
    op.create_index("ix_channeling_scheme_project_id", "channeling_scheme", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_channeling_scheme_project_id", table_name="channeling_scheme")
    op.drop_table("channeling_scheme")
    op.drop_index("ix_guardrail_rule_project_id", table_name="guardrail_rule")
    op.drop_table("guardrail_rule")
    op.drop_index("ix_conversational_variable_project_id", table_name="conversational_variable")
    op.drop_table("conversational_variable")
    op.drop_index("ix_intent_project_id", table_name="intent")
    op.drop_table("intent")
