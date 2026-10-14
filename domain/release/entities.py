"""Entidades del contexto Liberación (Etapa 7: "documentación y
liberación" -- compuertas de avance, dictamen y entregables formales).

RAG STUDIO.odt exige que "la aplicación debe imponer" la metodología en
vez de depender de que el usuario la recuerde: las compuertas de este
módulo son la verificación automática de que cada etapa previa (2-6)
cumple su "Debe existir" mínimo antes de permitir una liberación.

Alcance decidido para esta iteración (ver README, "Limitaciones
conocidas", para el detalle): se evalúan compuertas de metadatos,
fragmentación, pipeline, índice, diseño conversacional y calidad --
NO se agrega una compuerta de "Objetivo/Usuarios/Alcance/Fuentes
iniciales/Riesgo" a nivel de proyecto porque `Project` no tiene esos
campos y agregarlos sería alcance de Etapa 1, no de Etapa 7. Tampoco se
retrofita un bloqueo preventivo dentro de cada pestaña anterior (p. ej.
impedir crear un chunk sin esquema aprobado) -- las compuertas se
evalúan al solicitar una liberación, no en cada acción de las etapas
2-6."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReleaseStatus(str, Enum):
    """Los 8 valores exactos del documento maestro para el estado de
    una liberación."""

    NO_INICIADA = "no_iniciada"
    EN_PREPARACION = "en_preparacion"
    EN_EJECUCION = "en_ejecucion"
    EN_REVISION = "en_revision"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    BLOQUEADA = "bloqueada"
    SUSTITUIDA = "sustituida"


class GateResult(BaseModel):
    """El resultado de evaluar una compuerta individual (una de las
    verificaciones "Debe existir" del documento maestro para una
    etapa concreta)."""

    name: str
    """Nombre legible de la compuerta, p. ej. "Diseño conversacional"."""
    passed: bool
    reason: str
    """Explicación humana de por qué pasó o falló -- lo que se muestra
    en el dictamen, no solo el booleano."""


class ReleaseChecklist(BaseModel):
    """El conjunto de compuertas evaluadas para una solicitud de
    liberación."""

    gates: list[GateResult] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

    @property
    def failed_gates(self) -> list[GateResult]:
        return [gate for gate in self.gates if not gate.passed]


class ReleaseRecord(BaseModel):
    """Una solicitud de liberación evaluada. Se conserva el historial
    completo (igual que PipelineRun/EvaluationRun) -- una liberación
    rechazada o bloqueada no se sobrescribe, queda como evidencia de
    que se intentó y por qué no procedió."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    status: ReleaseStatus
    checklist: ReleaseChecklist
    dictamen: str
    """Texto de resumen humano del resultado -- aprobación, rechazo o
    bloqueo, y motivo principal."""
    evidence: dict[str, Optional[str]] = Field(default_factory=dict)
    """Referencias de las versiones congeladas evaluadas (p. ej.
    {"pipeline_run_id": ..., "evaluation_run_id": ...}) -- la
    trazabilidad de qué corridas concretas respaldan esta liberación."""
    deliverables_report: dict[str, Any] = Field(default_factory=dict)
    """Los 8 entregables formales (A/B del documento maestro),
    compilados a partir de los seis contextos previos -- ver
    application/release/queries/generate_deliverables_report.py."""
    created_at: datetime = Field(default_factory=_utcnow)


class ProjectSnapshot(BaseModel):
    """Instantánea de solo lectura del estado en disco de un proyecto
    (project.db + índice Qdrant + demás subcarpetas), publicada en un
    directorio versionado separado de projects/<project_id> -- donde
    la app de escritorio sigue editando en vivo.

    Existe para un futuro runtime de producción (ver
    docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx) que
    necesita leer un estado certificado sin competir con la app de
    escritorio por el lock exclusivo que QdrantClient(path=...) toma
    sobre su directorio mientras está abierto
    (infrastructure/filesystem/qdrant_local_store.py). No forma parte
    del alcance original de Etapa 7 (ADR-001) -- es la Fase 1 del plan
    de ADR-002.

    Publicar una instantánea es deliberadamente independiente de
    solicitar una liberación formal (ver PublishProjectSnapshot):
    mismo criterio que ya usan ExportProject/BackupProject en el
    contexto Proyectos -- no exige haber pasado las compuertas de
    calidad."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    version: int
    """Entero incremental por proyecto (1, 2, 3...), independiente del
    id de cualquier ReleaseRecord -- una instantánea puede publicarse
    sin pasar por una solicitud de liberación."""
    source_release_id: Optional[str] = None
    """El ReleaseRecord.id aprobado a partir del cual se publicó, si
    aplica -- trazabilidad opcional, no una dependencia dura."""
    snapshot_dir: str
    """Ruta absoluta del directorio publicado."""
    created_at: datetime = Field(default_factory=_utcnow)


class DeploymentPackage(BaseModel):
    """Paquete de entrega para quien vaya a desplegar/operar el runtime
    de producción (ADR-002) por cuenta del cliente final -- distinto
    del paquete de gobernanza de Etapa 7 (ver ReleasePackager, que
    empaqueta evidencia de calidad/proceso, no artefactos de
    despliegue). Responde al hallazgo de la Ronda 10 (ver
    Validacion_observaciones_RAG_STUDIO.md): con las 5 fases de
    ADR-002 cerradas, nada armaba un solo entregable con la instantánea
    publicada (Fase 1), un token de widget acotado por proyecto (Fase
    4), el snippet de embebido (Fase 3) y las instrucciones de
    despliegue de `interfaces/api/` (Fase 2/4) -- cada pieza vivía
    aislada en su propia fase, probada, pero nunca ensamblada para
    entregarla a un operador externo.

    Deliberadamente sin persistencia propia (no existe
    DeploymentPackageRepository): se recalcula al vuelo con datos ya
    existentes (ProjectSnapshot, un WidgetToken recién emitido) cada
    vez que se exporta -- mismo criterio que
    GenerateDeliverablesReport, que tampoco guarda un estado
    intermedio entre una exportación y otra.

    El contenido descriptivo (`informe`, `guia_despliegue`,
    `env_example`, `widget_snippet`, `contrato_integracion`) se genera en application
    (ExportDeploymentPackage) -- este modelo solo lo transporta hacia
    el empaquetador de infrastructure, mismo criterio que
    `ReleaseRecord.dictamen`/`deliverables_report` (texto de negocio
    ya resuelto, que el packager solo serializa a disco)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """Ronda 95: identificador de ESTA exportación física (cada exportación
    recibe uno nuevo, también si es la misma instantánea). Viaja en
    manifest.json como `deployment_package_id` y, por compatibilidad, como
    `package_id`. NO es la identidad lógica del conocimiento: para agrupar
    versiones sucesivas se usa `project_id` (y, cuando exista RAG-INC-01,
    `knowledge_base_id`). No debe volverse persistente."""
    project_id: str
    project_name: str
    snapshot_version: int
    snapshot_dir: str
    snapshot_id: Optional[str] = None
    """Ronda 95: `ProjectSnapshot.id` de la instantánea entregada -- igual en
    todas las exportaciones de la MISMA versión publicada."""
    """Ruta absoluta de la instantánea publicada que se está
    entregando -- el empaquetador copia su contenido completo dentro
    del paquete final (ver FilesystemDeploymentPackager)."""
    widget_token: str
    """Valor en texto plano de un token de widget recién emitido
    específicamente para esta entrega -- se muestra una sola vez,
    igual criterio que WidgetTokenResponse (ver
    interfaces/api/schemas.py): después de exportado, solo queda
    dentro del paquete ya entregado; quien lo reciba puede revocarlo y
    emitir uno nuevo vía `POST /projects/{id}/widget-tokens` en
    cualquier momento."""
    widget_token_id: str
    """`WidgetToken.id` (no el valor del token) -- auditoría Ronda 10,
    hallazgo B7: sin esto, revocar el token de este paquete exigía
    adivinar cuál de varios tokens del proyecto es, porque
    `WidgetTokenSummary` (la respuesta de listar) nunca expone el
    valor real. Con el id documentado en la guía, `DELETE
    /projects/{id}/widget-tokens/{widget_token_id}` identifica sin
    ambigüedad el token exacto que trae este paquete."""
    informe: str
    """Informe formal de la entrega, en prosa, dirigido al cliente no
    técnico: qué se le está entregando, para qué sirve cada pieza, y
    qué NO incluye este paquete (alcance)."""
    guia_despliegue: str
    """Guía técnica para quien vaya a operar el runtime: cómo instalar
    el extra `api`, qué variables de entorno definir, cómo arrancar
    `uvicorn`, cómo embeber el widget, cómo configurar canalización."""
    env_example: str
    """Plantilla de variables de entorno (formato .env), con las
    mismas variables ya documentadas en interfaces/api/app.py."""
    widget_snippet: str
    """El <script> listo para pegar en el sitio del cliente, ya con
    `data-project-id` y `data-widget-token` resueltos (falta solo
    `data-api-base`, que depende de dónde quede publicado el
    servicio -- no algo que esta instalación pueda saber de
    antemano)."""
    contrato_integracion: str
    """Ronda 19 (ver Validacion_observaciones_RAG_STUDIO.md,
    recomendación #3 de la evaluación de grado profesional -- Ronda
    18): a diferencia de `guia_despliegue` (cómo instalar y operar el
    SERVICIO), este documento es para quien construye o mantiene el
    AGENTE CONVERSACIONAL EXTERNO que va a consumir la materia prima
    que expone `POST /messages` -- la forma real de la solicitud/
    respuesta, qué significa cada valor de `action`, y una plantilla de
    system prompt recomendada para el LLM generador que ese agente
    externo aporte (RAG STUDIO nunca genera lenguaje natural, ver
    `application/runtime/commands/handle_incoming_message.py`). Sin
    este documento, integrar bien la materia prima dependía de que
    alguien leyera el código fuente de `interfaces/api/`."""
    created_at: datetime = Field(default_factory=_utcnow)
