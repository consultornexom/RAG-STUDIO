"""Etapa 2: gobierno documental y metamodelo de metadatos.

Añade: source, metadata_schema, field_definition, catalog,
catalog_entry, source_metadata_value.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("location", sa.String, nullable=False, server_default=""),
        sa.Column("owner_area", sa.String, nullable=True),
        sa.Column("access_level", sa.String, nullable=False),
        sa.Column("language", sa.String, nullable=False, server_default="es"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String, nullable=True),
        sa.Column("validation_status", sa.String, nullable=False),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("source_authority", sa.Integer, nullable=True),
        sa.Column("supersedes_source_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_project_id", "source", ["project_id"])
    op.create_index("ix_source_content_hash", "source", ["content_hash"])

    op.create_table(
        "metadata_schema",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_metadata_schema_project_id", "metadata_schema", ["project_id"])

    op.create_table(
        "field_definition",
        sa.Column("schema_id", sa.String, primary_key=True),
        sa.Column("field_id", sa.String, primary_key=True),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("data_type", sa.String, nullable=False),
        sa.Column("required", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("filterable", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("multiple", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("inherited_by_chunks", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("catalog_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "catalog",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalog_project_id", "catalog", ["project_id"])

    op.create_table(
        "catalog_entry",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("catalog_id", sa.String, nullable=False),
        sa.Column("value_code", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("parent_entry_id", sa.String, nullable=True),
        sa.UniqueConstraint("catalog_id", "value_code", name="uq_catalog_entry_code"),
    )
    op.create_index("ix_catalog_entry_catalog_id", "catalog_entry", ["catalog_id"])

    op.create_table(
        "source_metadata_value",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("field_id", sa.String, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "field_id", name="uq_source_metadata_field"),
    )
    op.create_index("ix_source_metadata_value_source_id", "source_metadata_value", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_source_metadata_value_source_id", table_name="source_metadata_value")
    op.drop_table("source_metadata_value")
    op.drop_index("ix_catalog_entry_catalog_id", table_name="catalog_entry")
    op.drop_table("catalog_entry")
    op.drop_index("ix_catalog_project_id", table_name="catalog")
    op.drop_table("catalog")
    op.drop_table("field_definition")
    op.drop_index("ix_metadata_schema_project_id", table_name="metadata_schema")
    op.drop_table("metadata_schema")
    op.drop_index("ix_source_content_hash", table_name="source")
    op.drop_index("ix_source_project_id", table_name="source")
    op.drop_table("source")
