"""Etapa 8: registro global de complementos (plantillas, proveedores,
importadores, evaluadores personalizados).

A diferencia de todas las tablas de las Etapas 2-7 (que viven en la
línea de migración `project/`, dentro del `project.db` de cada
proyecto), `plugin` vive en la línea `global/` (`application.db`): un
complemento no pertenece a un proyecto.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("version", sa.String, nullable=False, server_default="0.1.0"),
        sa.Column("entry_point", sa.String, nullable=True),
        sa.Column("config", sa.Text, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "code", name="uq_plugin_kind_code"),
    )
    op.create_index("ix_plugin_kind", "plugin", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_plugin_kind", table_name="plugin")
    op.drop_table("plugin")
