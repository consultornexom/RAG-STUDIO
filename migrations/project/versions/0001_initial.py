"""Esquema inicial por proyecto: registro de proyecto y configuración.

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("agent_type_hint", sa.String, nullable=True),
        sa.Column("description", sa.String, nullable=False, server_default=""),
        sa.Column("domain", sa.String, nullable=True),
        sa.Column("target_users", sa.String, nullable=True),
        sa.Column("language", sa.String, nullable=False, server_default="es"),
        sa.Column("risk_level", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("template_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "configuration",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_configuration_project_id", "configuration", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_configuration_project_id", table_name="configuration")
    op.drop_table("configuration")
    op.drop_table("project")
