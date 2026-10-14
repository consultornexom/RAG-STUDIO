"""Entidades del contexto Proyectos y configuración (ADR-001, sección 5).

Deliberadamente genéricas: ningún campo de negocio de un sector (por
ejemplo "plantel" o "producto") aparece aquí. Esos campos viven como
FieldDefinition dentro de un MetadataSchema (Etapa 2), nunca como
atributos fijos de Project.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .exceptions import InvalidStatusTransitionError


class ProjectStatus(str, Enum):
    """Estados sugeridos por el Documento Maestro / RAG STUDIO.odt, sección 8."""

    INICIAL = "inicial"
    EN_CONFIGURACION = "en_configuracion"
    EN_CONSTRUCCION = "en_construccion"
    EN_PRUEBAS = "en_pruebas"
    APROBADO = "aprobado"
    LIBERADO = "liberado"
    ARCHIVADO = "archivado"


# Transiciones permitidas. Un proyecto archivado nunca vuelve a moverse
# automáticamente; reactivarlo es una decisión explícita fuera de este
# grafo (no se modela en Etapa 1).
_ALLOWED_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.INICIAL: {ProjectStatus.EN_CONFIGURACION, ProjectStatus.ARCHIVADO},
    ProjectStatus.EN_CONFIGURACION: {ProjectStatus.EN_CONSTRUCCION, ProjectStatus.ARCHIVADO},
    ProjectStatus.EN_CONSTRUCCION: {ProjectStatus.EN_PRUEBAS, ProjectStatus.ARCHIVADO},
    ProjectStatus.EN_PRUEBAS: {ProjectStatus.APROBADO, ProjectStatus.EN_CONSTRUCCION, ProjectStatus.ARCHIVADO},
    ProjectStatus.APROBADO: {ProjectStatus.LIBERADO, ProjectStatus.ARCHIVADO},
    ProjectStatus.LIBERADO: {ProjectStatus.ARCHIVADO},
    ProjectStatus.ARCHIVADO: set(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(BaseModel):
    """Raíz de agregado del contexto Proyectos.

    Un Project es la unidad portable como .agentproj (ADR-001, sección
    8/13). El "tipo de agente" es solo orientativo: nunca impone reglas
    ni campos rígidos (RAG STUDIO.odt, sección 5).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    knowledge_base_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """RAG-INC-01a (migración 0021): identidad lógica portable de la base de
    conocimiento del proyecto (contrato NEXOM Knowledge Package v1.0.0).
    UUID4 asignado una sola vez y persistido; a diferencia de `id`, no cambia
    al importar el proyecto en otra instalación. Nunca se recalcula."""
    name: str
    agent_type_hint: Optional[str] = None
    description: str = ""
    domain: Optional[str] = None
    target_users: Optional[str] = None
    language: str = "es"
    risk_level: Optional[str] = None
    status: ProjectStatus = ProjectStatus.INICIAL
    template_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    archived_at: Optional[datetime] = None
    quality_regression_threshold: Optional[float] = None
    """Ronda 53 (Propuesta de evaluación continua reforzada, opción B'
    confirmada por el consultor): caída relativa máxima admitida de
    Recall@3/MRR entre dos corridas "completa" consecutivas, antes de
    que la compuerta de liberación "Regresión de recuperación" bloquee
    (ver application/release/queries/evaluate_release_gates.py). None
    significa "usar el valor por defecto de la instalación" (ver
    application/quality/options.py::DEFAULT_QUALITY_REGRESSION_
    THRESHOLD) -- deliberadamente distinto de los siete campos
    descriptivos de más arriba (agent_type_hint...template_id): este no
    es un campo de negocio del proyecto, es un parámetro técnico del
    motor de evaluación continua, y se edita desde el panel de Calidad,
    no desde _ProjectDetailsDialog."""

    @field_validator("quality_regression_threshold")
    @classmethod
    def _threshold_en_rango(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("El umbral de regresión debe estar entre 0.0 y 1.0 (fracción, no porcentaje)")
        return v

    @model_validator(mode="before")
    @classmethod
    def _sync_fresh_timestamps(cls, data):
        """Un proyecto recien creado no tiene todavia una actualizacion:
        created_at y updated_at deben coincidir exactamente, no solo
        estar cerca en el tiempo."""
        if isinstance(data, dict) and "created_at" not in data and "updated_at" not in data:
            now = _utcnow()
            data["created_at"] = now
            data["updated_at"] = now
        return data

    @field_validator("name")
    @classmethod
    def _name_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre del proyecto no puede estar vacío")
        return v

    def transition_to(self, target: ProjectStatus) -> "Project":
        """Devuelve una copia con el nuevo estado, validando la transición.

        Nunca aprueba automáticamente contenido crítico: esta función solo
        mueve el estado administrativo del proyecto, no sustituye la
        aprobación humana exigida en compuertas posteriores.
        """
        allowed = _ALLOWED_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise InvalidStatusTransitionError(self.status.value, target.value)
        data = self.model_dump()
        data["status"] = target
        data["updated_at"] = _utcnow()
        if target == ProjectStatus.ARCHIVADO:
            data["archived_at"] = _utcnow()
        return Project(**data)

    def is_archived(self) -> bool:
        return self.status == ProjectStatus.ARCHIVADO

    def allowed_next_statuses(self) -> set[ProjectStatus]:
        """Ronda 15, punto 48 (backlog resuelto): expone el mismo grafo
        que ya valida transition_to(), en vez de que cada capa superior
        (application/ui) reimplemente o adivine qué transiciones son
        válidas. `_ALLOWED_TRANSITIONS` se queda privado del módulo --
        esta es la única forma pública de consultarlo, para no invitar
        a que otro código dependa de su forma interna (un dict)."""
        return set(_ALLOWED_TRANSITIONS.get(self.status, set()))


class ConfigurationEntry(BaseModel):
    """Un valor de configuración versionado, congelado por corrida.

    El valor se guarda como texto (JSON-serializado por quien lo use);
    domain no impone un esquema de configuración específico.
    """

    project_id: str
    key: str
    value: str
    version: int = 1
    created_at: datetime = Field(default_factory=_utcnow)


class Template(BaseModel):
    """Plantilla de inicio para un proyecto. Nunca impone reglas rígidas,
    solo carga valores iniciales (RAG STUDIO.odt, sección 6)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    sector_hint: Optional[str] = None
    default_fields: dict[str, str] = Field(default_factory=dict)
