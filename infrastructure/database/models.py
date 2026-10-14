"""Modelos SQLAlchemy. Dos esquemas independientes (ADR-001, sección 9):

- GlobalBase  -> application.db: índice ligero de proyectos, preferencias,
  plantillas, catálogos reutilizables (Etapa 1 solo implementa el índice
  de proyectos; el resto se añade cuando exista su caso de uso).
- ProjectBase -> project.db (uno por proyecto): el registro autoritativo
  del proyecto y su configuración versionada. Nunca contiene datos de
  otro proyecto, para que sea portable de forma independiente.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .utc_datetime import UTCDateTime


class GlobalBase(DeclarativeBase):
    pass


class ProjectIndexRecord(GlobalBase):
    """Entrada de historial de proyectos en la base global.

    Permite listar proyectos sin abrir cada project.db. El registro
    autoritativo de cada proyecto vive en su propio project.db.
    """

    __tablename__ = "project_index"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class PluginRecord(GlobalBase):
    """Complemento registrado en la instalación (Etapa 8). A diferencia
    de todo lo demás en `GlobalBase`, no es un índice de algo que vive
    en otro lado: es el registro autoritativo del complemento -- vive
    aquí porque un complemento no pertenece a un proyecto, está
    disponible para todos."""

    __tablename__ = "plugin"
    __table_args__ = (UniqueConstraint("kind", "code", name="uq_plugin_kind_code"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String, nullable=False, default="0.1.0")
    entry_point: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    """Dict[str, Any] serializado en JSON."""
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectBase(DeclarativeBase):
    pass


class ProjectRecord(ProjectBase):
    """Registro autoritativo del proyecto, dentro de su propio project.db."""

    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    """RAG-INC-01a (migración 0021): UUID4 persistente, ver Project.knowledge_base_id."""
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    agent_type_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    target_users: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False, default="es")
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    template_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    quality_regression_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Ronda 53 (Propuesta de evaluación continua reforzada, opción B'
    confirmada por el consultor): caída relativa máxima admitida de
    Recall@3/MRR entre dos corridas "completa" consecutivas antes de que
    la compuerta de liberación "Regresión de recuperación" bloquee. NULL
    significa "usar el valor por defecto de la instalación"
    (DEFAULT_QUALITY_REGRESSION_THRESHOLD, ver application/quality/
    options.py) -- ningún proyecto existente necesita backfill."""


class ConfigurationRecord(ProjectBase):
    """Configuración versionada, dentro del project.db de su proyecto."""

    __tablename__ = "configuration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class SourceRecord(ProjectBase):
    """Fuente gobernada (contexto Documentos), dentro del project.db."""

    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False, default="")
    owner_area: Mapped[str | None] = mapped_column(String, nullable=True)
    access_level: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="es")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    validation_status: Mapped[str] = mapped_column(String, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_authority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supersedes_source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lineage_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """RAG-INC-01a (migración 0021): ver Source.lineage_id."""
    original_copy_path: Mapped[str | None] = mapped_column(String, nullable=True)
    document_type_code: Mapped[str] = mapped_column(String, nullable=False, server_default="default")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class MetadataSchemaRecord(ProjectBase):
    """Esquema de metadatos versionado (contexto Metadatos)."""

    __tablename__ = "metadata_schema"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class FieldDefinitionRecord(ProjectBase):
    """Definición de campo del metamodelo. Clave compuesta
    (schema_id, field_id): field_id es estable dentro de su esquema."""

    __tablename__ = "field_definition"

    schema_id: Mapped[str] = mapped_column(String, primary_key=True)
    field_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    data_type: Mapped[str] = mapped_column(String, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    multiple: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inherited_by_chunks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    catalog_id: Mapped[str | None] = mapped_column(String, nullable=True)
    document_type_code: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CatalogRecord(ProjectBase):
    __tablename__ = "catalog"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CatalogEntryRecord(ProjectBase):
    """Entrada de catálogo, opcionalmente jerárquica vía parent_entry_id."""

    __tablename__ = "catalog_entry"
    __table_args__ = (UniqueConstraint("catalog_id", "value_code", name="uq_catalog_entry_code"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    catalog_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    value_code: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    parent_entry_id: Mapped[str | None] = mapped_column(String, nullable=True)


class SourceMetadataValueRecord(ProjectBase):
    """Valor vigente de un campo para una fuente (upsert por
    source_id+field_id -- el historial de auditoría de cambios vive en
    MetadataValueChangeRecord, tabla aparte de solo inserción)."""

    __tablename__ = "source_metadata_value"
    __table_args__ = (UniqueConstraint("source_id", "field_id", name="uq_source_metadata_field"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    field_id: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class MetadataValueChangeRecord(ProjectBase):
    """Historial de auditoría (ítem 5 de la evaluación de madurez
    post-8-etapas): una fila por cada vez que
    SqlAlchemySourceMetadataRepository.save_value cambió de verdad el
    valor vigente de un campo para una fuente. Tabla de solo
    inserción -- nunca se actualiza ni se borra una fila existente."""

    __tablename__ = "metadata_value_change"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    field_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    previous_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    """Nullable desde la migración 0012 (Ronda 6, punto 23): None
    identifica que DeleteSourceMetadataValue quitó el valor vigente --
    antes esta columna solo registraba cambios de un valor a otro,
    nunca a "sin asignar"."""
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExtractionRecordRecord(ProjectBase):
    """Resultado de extraer texto de una Source (contexto Ingesta,
    Etapa 3): la extracción VIGENTE, una por fuente (upsert) -- el
    historial de auditoría de extracciones anteriores vive en
    ExtractionRecordHistoryRecord, tabla aparte de solo inserción."""

    __tablename__ = "extraction_record"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_breaks: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de enteros serializada en JSON."""
    extraction_method: Mapped[str] = mapped_column(String, nullable=False, default="")
    warnings: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    structured_blocks: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Pista B.2 del ADR-003: dict serializado en JSON (ver
    ExtractionRecord.structured_blocks). Nullable -- migración
    0015, aditiva: filas creadas antes de esa migración quedan en
    NULL, que el repositorio trata como "{}" (sin backfill)."""
    extracted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExtractionRecordHistoryRecord(ProjectBase):
    """Historial de auditoría (ítem 5 de la evaluación de madurez
    post-8-etapas): una fila por cada llamada a
    SqlAlchemyExtractionRepository.save, incluida la primera -- a
    diferencia de MetadataValueChangeRecord, no se filtra por "¿cambió
    de verdad el texto?" (cada corrida de extracción es un evento real
    por sí mismo). Tabla de solo inserción, con su propio id (no
    reutiliza el id de ExtractionRecordRecord)."""

    __tablename__ = "extraction_record_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_breaks: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    extraction_method: Mapped[str] = mapped_column(String, nullable=False, default="")
    warnings: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    structured_blocks: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Ver ExtractionRecordRecord.structured_blocks -- misma migración
    0015, mismo criterio de compatibilidad hacia atrás."""
    extracted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ChunkRecord(ProjectBase):
    """Fragmento resultante de fragmentar una Source (contexto
    Ingesta, Etapa 3)."""

    __tablename__ = "chunk"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_type: Mapped[str] = mapped_column(String, nullable=False)
    previous_chunk_id: Mapped[str | None] = mapped_column(String, nullable=True)
    next_chunk_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_chunk_id: Mapped[str | None] = mapped_column(String, nullable=True)
    """Pista B.1 del ADR-003 (migración 0014) -- sin FK real, mismo
    criterio que previous_chunk_id/next_chunk_id."""
    structured_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Pista B.1 del ADR-003 (migración 0014) -- dict serializado en
    JSON, o NULL si el fragmento no tiene contenido estructurado."""
    semantic_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    inherited_metadata: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    """Dict[str, str] serializado en JSON."""
    pipeline_version: Mapped[str] = mapped_column(String, nullable=False, default="1.0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    image_relative_path: Mapped[str | None] = mapped_column(String, nullable=True)
    """Migración 0020 (Ronda 68): ver domain.ingestion.entities.
    Chunk.image_relative_path -- solo poblado para ChunkType.IMAGEN
    (Fase 3 de multimodalidad nativa, RAG 3); NULL para cualquier otro
    tipo de chunk."""


class PipelineRunRecord(ProjectBase):
    """Corrida del pipeline reproducible sobre todas las fuentes de un
    proyecto (Etapa 3, "pipeline reproducible"). Se conserva el
    historial completo de corridas -- a diferencia de la mayoría de las
    tablas de este proyecto, que guardan solo el estado vigente
    (upsert)."""

    __tablename__ = "pipeline_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    document_type_code: Mapped[str] = mapped_column(String, nullable=False, default="default")
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PipelineRunItemRecord(ProjectBase):
    """Resultado de procesar una fuente dentro de una PipelineRun.
    project_id se guarda también aquí (no solo en pipeline_run) para
    poder buscar "el último item exitoso de esta fuente en cualquier
    corrida" sin tener que unir contra pipeline_run en cada consulta de
    incrementalidad."""

    __tablename__ = "pipeline_run_item"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    steps_completed: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    chunks_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class FragmentationPolicyRecord(ProjectBase):
    """Parámetros de fragmentación configurables por
    document_type_code (contexto Ingesta, Etapa 3)."""

    __tablename__ = "fragmentation_policy"
    __table_args__ = (UniqueConstraint("project_id", "document_type_code", name="uq_fragmentation_policy_code"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    document_type_code: Mapped[str] = mapped_column(String, nullable=False)
    strategy: Mapped[str] = mapped_column(String, nullable=False)
    target_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    overlap_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    min_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class IndexInfoRecord(ProjectBase):
    """Estado vigente del indice vectorial de un proyecto (contexto
    RAG, Etapa 4). Un registro por proyecto (upsert por project_id) --
    misma convencion que ExtractionRecordRecord: guarda el estado
    actual, no historial de reindexaciones."""

    __tablename__ = "index_info"

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    embedding_provider: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    points_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class IntentRecord(ProjectBase):
    """Intención conversacional (Etapa 5, "Diseño conversacional").
    Upsert por id -- igual que la mayoría de las tablas de
    configuración de este proyecto (no se conserva historial de
    ediciones, solo la versión vigente)."""

    __tablename__ = "intent"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    positive_examples: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    negative_examples: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="bajo")
    required_variables: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    optional_variables: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    clarifying_questions: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    """Dict[str, str] serializado en JSON."""
    response_rule: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fallback_channeling_code: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution_mode: Mapped[str] = mapped_column(String, nullable=False, default="semantico")
    """Pista B.4 del ADR-003 (migración 0016) -- ver
    domain.conversational.entities.IntentResolutionMode."""
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ConversationalVariableRecord(ProjectBase):
    """Variable conversacional (Etapa 5) -- puente documentado "Dato
    conversacional → Campo de metadatos → Filtro de recuperación"."""

    __tablename__ = "conversational_variable"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_conversational_variable_code"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_field_id: Mapped[str | None] = mapped_column(String, nullable=True)
    structured_column: Mapped[str | None] = mapped_column(String, nullable=True)
    """Pista B.4 del ADR-003 (migración 0016) -- ver
    domain.conversational.entities.ConversationalVariable.structured_column."""
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class GuardrailRuleRecord(ProjectBase):
    """Regla del catálogo de guardrails (Etapa 5)."""

    __tablename__ = "guardrail_rule"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    conditions: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de {"field", "operator", "value"} serializada en JSON."""
    action: Mapped[str] = mapped_column(String, nullable=False, default="responder")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ChannelingSchemeRecord(ProjectBase):
    """Esquema de canalización (Etapa 5) -- para esta versión, la
    canalización se simula (genera el paquete estructurado) en vez de
    integrarse con sistemas externos reales."""

    __tablename__ = "channeling_scheme"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_channeling_scheme_code"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    condition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_area: Mapped[str] = mapped_column(String, nullable=False, default="")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_data: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    allowed_data: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    forbidden_data: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    summary_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    medium: Mapped[str] = mapped_column(String, nullable=False, default="registro_manual")
    user_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    alternative_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class TestCaseRecord(ProjectBase):
    """Caso del banco de pruebas (Etapa 6, "Calidad"). Upsert por id --
    igual convención que la mayoría de las tablas de configuración de
    este proyecto."""

    __tablename__ = "test_case"
    __table_args__ = (
        # Auditoría Ronda 48 (pruebas reales con documentos de
        # Licenciatura/), hallazgo menor -- a diferencia de
        # ChannelingSchemeRecord (uq_channeling_scheme_code, arriba),
        # esta tabla no tenía ninguna restricción de unicidad sobre
        # `code`: se podían crear dos casos de prueba con el mismo
        # code (p. ej. dos "UDL-001" distintos) sin ningún error, lo
        # que vuelve ambiguo un reporte de evaluación (que identifica
        # cada resultado por test_case_code). Se usa un índice único en
        # vez de UniqueConstraint porque la tabla ya existe con datos
        # reales en instalaciones existentes -- SQLite no soporta
        # agregar una restricción con ALTER TABLE sin recrear la tabla
        # (modo "batch" de Alembic), pero sí soporta crear un índice
        # único de forma aditiva (migración 0017); la protección real
        # en la base de datos es idéntica.
        Index("uq_test_case_code", "project_id", "code", unique=True),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    provided_variables: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    """Dict[str, str] serializado en JSON."""
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_intent: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_missing_variable: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_action: Mapped[str | None] = mapped_column(String, nullable=True)
    forbidden_action: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_channeling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="media")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class EvaluationRunRecord(ProjectBase):
    """Corrida del banco de pruebas (Etapa 6). Se conserva el
    historial completo de corridas -- igual criterio que PipelineRun:
    el documento maestro exige comparar corridas pasadas (regresión),
    no solo ver la última."""

    __tablename__ = "evaluation_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String, nullable=False, default="completa")
    category_filter: Mapped[str | None] = mapped_column(String, nullable=True)
    test_case_id_filter: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class EvaluationResultItemRecord(ProjectBase):
    """Resultado de un TestCase dentro de una EvaluationRun."""

    __tablename__ = "evaluation_result_item"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    test_case_code: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actual_intent: Mapped[str | None] = mapped_column(String, nullable=True)
    actual_action: Mapped[str | None] = mapped_column(String, nullable=True)
    actual_channeling_code: Mapped[str | None] = mapped_column(String, nullable=True)
    mismatches: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    """Lista de strings serializada en JSON."""
    regressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_check_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """Ronda 53 (corrige una brecha de persistencia real, ver
    migración 0018): antes de esta columna, este campo y
    expected_source_rank existían en el dominio (ADR-003, Pista A.1)
    pero nunca se guardaban ni se releían -- recall_at_k()/
    mean_reciprocal_rank() devolvían None para cualquier corrida cargada
    de BD (todo el historial), aunque la corrida sí tuviera casos con
    fuente esperada. Solo sobrevivía en el objeto en memoria devuelto
    directo por RunEvaluation.execute(), nunca tras un roundtrip real."""
    expected_source_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ReleaseRecordRecord(ProjectBase):
    """Solicitud de liberación evaluada (Etapa 7). Se conserva el
    historial completo -- igual criterio que PipelineRun/
    EvaluationRun: una liberación bloqueada o rechazada queda como
    evidencia de que se intentó y por qué no procedió."""

    __tablename__ = "release_record"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    checklist: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    """ReleaseChecklist serializado en JSON (list[GateResult])."""
    dictamen: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    """Dict[str, Optional[str]] serializado en JSON."""
    deliverables_report: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    """Dict serializado en JSON con los 8 entregables formales."""
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectSnapshotRecord(ProjectBase):
    """Instantánea publicada de un proyecto (ADR-002, Fase 1). Se
    conserva el historial completo -- mismo criterio que
    ReleaseRecord/PipelineRun: cada publicación es una entrada nueva,
    nunca se sobrescribe."""

    __tablename__ = "project_snapshot"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_release_id: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot_dir: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
