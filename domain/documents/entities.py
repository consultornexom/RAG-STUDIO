"""Entidad Source (ADR-001, sección 5 — contexto "Documentos").

Separa explícitamente tres conceptos que RAG STUDIO INVESTIGACION.odt
advierte no deben confundirse:

- Vigencia (valid_from/valid_to): si el contenido aplica hoy.
- Validación (validation_status): si el contenido fue revisado y
  autorizado para uso conversacional.
- Autoridad (source_authority): qué fuente prevalece frente a otra
  cuando hay contradicción. Es independiente de las otras dos.

Un documento puede estar validado pero ya no vigente, o vigente pero
todavía no validado.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .exceptions import InvalidValidationTransitionError


class SourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    HTML = "html"
    TXT = "txt"
    MARKDOWN = "markdown"
    JSON = "json"
    XML = "xml"
    IMAGEN_ESCANEADA = "imagen_escaneada"
    IMAGEN_NATIVA = "imagen_nativa"
    """Fase 2 de multimodalidad nativa (RAG 3, ver docs proyecto/
    RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx). Deliberadamente
    distinto de IMAGEN_ESCANEADA, aunque ambos partan del mismo tipo de
    archivo (JPG/PNG/...): IMAGEN_ESCANEADA existe para transcribir texto
    vía OCR (el contenido real es el texto que contiene la imagen);
    IMAGEN_NATIVA existe para búsqueda por similitud visual (el contenido
    real es la imagen misma -- no hay texto que transcribir). Ver
    infrastructure.extraction.text_extractors.ImageNativeExtractor."""
    API = "api"
    BASE_DE_DATOS = "base_de_datos"


NON_FILE_SOURCE_TYPES = frozenset({SourceType.API, SourceType.BASE_DE_DATOS})
"""Tipos de fuente cuya `location` no apunta a un archivo real en
disco (una API o una base de datos) -- usado por
application.documents (RegisterSource/UpdateSourceDetails) para saber
cuándo tiene sentido intentar una copia a sources/original/ (ver
domain.documents.ports.SourceFileStore); vive en domain porque es
vocabulario del tipo de fuente, no una decisión de infraestructura."""


class AccessLevel(str, Enum):
    PUBLICO = "publico"
    INTERNO = "interno"
    CONFIDENCIAL = "confidencial"
    RESTRINGIDO = "restringido"


_ACCESS_LEVEL_RANK: dict[AccessLevel, int] = {
    AccessLevel.PUBLICO: 0,
    AccessLevel.INTERNO: 1,
    AccessLevel.CONFIDENCIAL: 2,
    AccessLevel.RESTRINGIDO: 3,
}
"""Orden total explícito (Pista B.3 del ADR-003, control de acceso en
tiempo de consulta): AccessLevel es un Enum de str sin orden implícito
-- comparar "cuánto puede ver" un canal exige decidir de una vez cuál
de los cuatro valores es más permisivo que cuál. Si se agrega un
quinto valor a AccessLevel en el futuro, quien lo agregue DEBE
actualizar este dict explícitamente (no hay ningún mecanismo que lo
haga por sí solo) -- ver is_within_access_level, la única función que
lo consulta."""


def is_within_access_level(level: AccessLevel, ceiling: AccessLevel) -> bool:
    """True si `level` (el access_level de una fuente) no excede
    `ceiling` (el techo autorizado para quien consulta) -- p. ej.
    is_within_access_level(PUBLICO, INTERNO) es True (público es menos
    restrictivo que el techo), pero
    is_within_access_level(CONFIDENCIAL, INTERNO) es False. Vive en
    domain (no en application) por el mismo criterio que
    Source.is_usable_for_responses(): es una regla del dominio de
    documentos, no una decisión de infraestructura ni de application."""
    return _ACCESS_LEVEL_RANK[level] <= _ACCESS_LEVEL_RANK[ceiling]


class SourceValidationStatus(str, Enum):
    BORRADOR = "borrador"
    EN_REVISION = "en_revision"
    VALIDADO = "validado"
    SUSTITUIDO = "sustituido"
    VENCIDO = "vencido"
    RECHAZADO = "rechazado"


_ALLOWED_VALIDATION_TRANSITIONS: dict[SourceValidationStatus, set[SourceValidationStatus]] = {
    SourceValidationStatus.BORRADOR: {SourceValidationStatus.EN_REVISION, SourceValidationStatus.RECHAZADO},
    SourceValidationStatus.EN_REVISION: {
        SourceValidationStatus.VALIDADO, SourceValidationStatus.RECHAZADO, SourceValidationStatus.BORRADOR,
    },
    SourceValidationStatus.VALIDADO: {SourceValidationStatus.SUSTITUIDO, SourceValidationStatus.VENCIDO},
    SourceValidationStatus.SUSTITUIDO: set(),
    SourceValidationStatus.VENCIDO: set(),
    SourceValidationStatus.RECHAZADO: set(),
}

TERMINAL_VALIDATION_STATUSES: frozenset[SourceValidationStatus] = frozenset(
    status for status, targets in _ALLOWED_VALIDATION_TRANSITIONS.items() if not targets
)
"""Estados sin ninguna transición de salida permitida (hoy: SUSTITUIDO,
VENCIDO, RECHAZADO). Una vez que una fuente entra a uno de estos
estados, la única forma de "corregir" un error es registrar una fuente
nueva -- no existe, ni existirá desde `transition_validation_to`,
ningún camino de regreso: es gobierno documental deliberado (una vez
sustituida/vencida/rechazada formalmente, revertirlo en silencio
rompería la trazabilidad que este estado existe para dejar). Expuesto
como constante pública (en vez de dejar `_ALLOWED_VALIDATION_TRANSITIONS`
privada) para que la UI pueda advertir ANTES de aplicar la transición,
ya que confirmar por accidente no se puede deshacer -- hallazgo real de
usuario (ver Validacion_observaciones_RAG_STUDIO.md, Ronda 5): "cómo
actuar si un usuario selecciona un estado restrictivo por
equivocación". Ver ui.sources.panel.SourcesPanel._on_change_status."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(BaseModel):
    """Fuente gobernada dentro de un proyecto. Antes de A3 (Etapa 3),
    es la unidad de gobierno documental; después será también el
    documento padre de sus fragmentos."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    title: str
    source_type: SourceType
    location: str = ""
    owner_area: Optional[str] = None
    access_level: AccessLevel = AccessLevel.INTERNO
    language: str = "es"
    version: int = 1
    """Aclaración agregada en la Pista C.2c del ADR-003 (docs proyecto/
    RAG_STUDIO_Propuesta_C2_Procedencia_Temporalidad.docx), tras
    confirmar en el código real que este campo no participa de ningún
    flujo: ninguna función, comando ni repositorio de este proyecto lo
    incrementa jamás -- se persiste fielmente, pero vale 1 siempre. El
    mecanismo real de versionado de una fuente es
    `supersedes_source_id` (una fuente NUEVA, con su propio id, que
    sustituye a una anterior -- ver `application.documents.commands.
    register_source` y `application.documents.queries.
    get_source_lineage.GetSourceLineage`, que camina esa cadena
    completa). Se decidió no wire-uppear este campo para no mantener
    dos mecanismos paralelos de la misma idea -- si en el futuro se
    necesita reabrir esa decisión, ver la sección 4.3 del documento de
    diseño citado arriba."""
    content_hash: Optional[str] = None
    validation_status: SourceValidationStatus = SourceValidationStatus.BORRADOR
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source_authority: Optional[int] = None
    """Convención: 1 = máxima autoridad. None = no priorizada."""
    supersedes_source_id: Optional[str] = None
    document_type_code: str = "default"
    """Tipo de documento de la fuente (mismo vocabulario libre que
    domain.ingestion.entities.FragmentationPolicy.document_type_code,
    reutilizado aquí -- observación real de usuario, ver
    docs proyecto/Validacion_observaciones_RAG_STUDIO.md, punto 10):
    antes no existía ningún dato en Source que permitiera distinguir,
    por ejemplo, una fuente de "contactos" de una de "requisitos de
    admisión" -- el esquema de metadatos era plano y compartido por
    todas las fuentes del proyecto sin ninguna forma de acotar qué
    campos aplican a cuál.

    Se usa para filtrar qué FieldDefinition (ver domain.metadata.entities.
    fields_applicable_to) aplican a esta fuente en "Valores por fuente"
    y en el reporte de Cobertura: un campo con document_type_code=None
    es genérico y aplica a TODAS las fuentes sin importar el suyo; un
    campo con un document_type_code concreto solo aplica a las fuentes
    con ese mismo valor aquí. "default" es simplemente el valor inicial
    de una fuente sin tipo asignado explícitamente -- no es un valor
    especial ("comodín"): un campo etiquetado "default" NO aplica a una
    fuente con document_type_code="contactos". Los esquemas creados
    antes de este cambio no se ven afectados: todos sus campos quedan
    con document_type_code=None (genéricos), así que siguen aplicando a
    todas las fuentes exactamente como antes."""
    original_copy_path: Optional[str] = None
    """Ruta (dentro de `sources/original/` del proyecto) de la copia
    local del archivo original, si se pudo copiar al registrar la
    fuente (o al editar su ubicación mientras siga sin bloquear -- ver
    SourceStructuralFieldsLockedError). `None` cuando el tipo de fuente
    no es un archivo (api/base_de_datos), cuando `location` estaba
    vacía, o cuando la copia falló (p. ej. ruta no legible en ese
    momento) -- en cualquiera de esos casos, la extracción sigue
    leyendo de `location` directamente, igual que antes de este campo
    (ver ExtractSourceText.execute)."""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("title")
    @classmethod
    def _title_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El título de la fuente no puede estar vacío")
        return v

    @model_validator(mode="before")
    @classmethod
    def _sync_fresh_timestamps(cls, data):
        if isinstance(data, dict) and "created_at" not in data and "updated_at" not in data:
            now = _utcnow()
            data["created_at"] = now
            data["updated_at"] = now
        return data

    def with_updated_details(
        self, title: str, owner_area: Optional[str], access_level: AccessLevel,
        location: str, source_type: SourceType,
        valid_from: Optional[date] = None, valid_to: Optional[date] = None,
        source_authority: Optional[int] = None, document_type_code: str = "default",
        language: str = "es",
    ) -> "Source":
        """Devuelve una copia con los nueve campos editables desde la
        UI actualizados -- estilo "reemplazo completo" (como
        update_field_definition/update_catalog_entry en otros
        contextos), no un parche parcial: quien llama siempre manda
        los nueve valores vigentes en el diálogo de edición, editados
        o no.

        valid_from/valid_to/source_authority se agregaron después de
        que el manual de usuario ya los documentaba (sección 5.2/5.4)
        pero el formulario de la UI no los exponía -- ver
        ui.sources.panel._RegisterSourceDialog. document_type_code se
        agregó después, por la misma vía (ver docstring del campo).
        `language` se agregó igual (análisis de brechas dominio/UI a
        raíz de la nota de "valor múltiple" del Manual del Usuario,
        sección 6.1): el campo existe desde el alta de RegisterSource,
        pero antes no había ninguna forma de corregirlo después de
        registrar la fuente. Todos son descriptivos, igual que
        title/owner_area/access_level: no participan de la regla de
        bloqueo estructural de location/source_type (ver docstring de
        application.documents.commands.update_source_details), así que
        siempre son editables.

        No decide por sí sola si location/source_type PUEDEN cambiar
        en este momento -- esa regla depende de si ya existe una
        extracción guardada (contexto Ingesta), algo que Source no
        puede saber (domain no conoce otros contextos). La aplica
        application.documents.commands.update_source_details antes de
        llamar aquí; ver SourceStructuralFieldsLockedError."""
        data = self.model_dump()
        data["title"] = title
        data["owner_area"] = owner_area
        data["access_level"] = access_level
        data["location"] = location
        data["source_type"] = source_type
        data["valid_from"] = valid_from
        data["valid_to"] = valid_to
        data["source_authority"] = source_authority
        data["document_type_code"] = document_type_code
        data["language"] = language
        data["updated_at"] = _utcnow()
        return Source(**data)

    def transition_validation_to(self, target: SourceValidationStatus) -> "Source":
        # Se normaliza explícitamente: los llamadores de application/ui
        # pueden pasar el valor como string plano (p.ej. desde un combo
        # box), y sin este casteo target.value fallaría con AttributeError
        # en vez de reportar la transición inválida.
        target = SourceValidationStatus(target)
        allowed = _ALLOWED_VALIDATION_TRANSITIONS.get(self.validation_status, set())
        if target not in allowed:
            raise InvalidValidationTransitionError(self.validation_status.value, target.value)
        data = self.model_dump()
        data["validation_status"] = target
        data["updated_at"] = _utcnow()
        return Source(**data)

    def is_current(self, as_of: Optional[date] = None) -> bool:
        """Vigencia: ¿el contenido aplica en la fecha dada?"""
        as_of = as_of or datetime.now(timezone.utc).date()
        if self.valid_from is not None and as_of < self.valid_from:
            return False
        if self.valid_to is not None and as_of > self.valid_to:
            return False
        return True

    def is_usable_for_responses(self, as_of: Optional[date] = None) -> bool:
        """Campo explícito (RAG STUDIO INVESTIGACION.odt, A1) para decidir
        si esta fuente puede sustentar una respuesta: validada Y vigente.
        Deliberadamente no considera source_authority — eso resuelve
        contradicciones entre fuentes ya usables, no si una es usable."""
        return self.validation_status == SourceValidationStatus.VALIDADO and self.is_current(as_of)
