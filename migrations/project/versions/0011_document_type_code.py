"""Observación real de usuario (docs proyecto/Validacion_observaciones_RAG_STUDIO.md,
punto 10): el esquema de metadatos era único y plano por proyecto, sin
ninguna forma de acotar qué campos aplican a qué fuentes -- un campo
pensado para un tipo de documento (p. ej. "contactos") convivía en el
mismo esquema, sin distinción, con los de otro tipo totalmente
distinto (p. ej. "requisitos de admisión").

Añade `document_type_code` a `source` y a `field_definition`, mismo
vocabulario libre que ya usaba `FragmentationPolicy.document_type_code`
(contexto Ingesta) pero hasta ahora nunca persistido en `Source` ni
conectado al metamodelo de Metadatos:

- `source.document_type_code`: NOT NULL, default "default" (mismo
  valor por defecto que ya usaba Ingesta) -- toda fuente existente
  queda con "default" tras la migración, sin necesidad de backfill
  manual: es exactamente el mismo comportamiento que tenía antes de
  que este campo existiera (ningún tipo específico asignado).
- `field_definition.document_type_code`: NULLABLE, sin default -- NULL
  significa "campo genérico, aplica a toda fuente" (ver
  domain.metadata.entities.fields_applicable_to). Todos los campos ya
  existentes quedan en NULL, así que siguen aplicando a todas las
  fuentes del proyecto exactamente igual que antes de esta migración;
  ningún esquema existente cambia de comportamiento.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column("document_type_code", sa.String, nullable=False, server_default="default"),
    )
    op.add_column(
        "field_definition",
        sa.Column("document_type_code", sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("field_definition", "document_type_code")
    op.drop_column("source", "document_type_code")
