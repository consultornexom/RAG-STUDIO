"""Entidades del contexto Pipeline (Etapa 3, "pipeline reproducible":
documento maestro, fase 3 -- "descubrimiento a verificación, reanudación,
incrementalidad, errores, advertencias, versiones, tiempos y evidencias";
Compuerta 3 -- "corrida exitosa, errores, advertencias y trazabilidad...
no usar una corrida incompleta como base de índice").

Hasta esta iteración, extraer/fragmentar/indexar era siempre una acción
manual por fuente desde la pestaña Ingesta. `PipelineRun` representa
una corrida por lote sobre TODAS las fuentes de un proyecto (extraer +
fragmentar + indexar cada una), con:

- Trazabilidad: qué pasó con cada fuente (éxito, error, advertencias,
  qué pasos llegó a completar), no solo un resultado global.
- Incrementalidad: una fuente cuyo archivo no cambió desde su última
  corrida exitosa se omite (no se vuelve a extraer/fragmentar/indexar)
  -- ver PipelineRunItem.content_hash. Ronda 98 (hallazgo real de NEXOM,
  AGENTE UDL - LOTE01_Bachillerato): además del archivo, se comparan la
  política de fragmentación aplicable (policy_hash), los metadatos que
  heredan los fragmentos (metadata_hash) y los fragmentos guardados
  (chunks_digest); si cualquiera cambió, la fuente se reprocesa aunque el
  archivo sea el mismo. `reason` deja escrita la causa de cada decisión.
- Política por fuente (Ronda 98): cada fuente se fragmenta con la política
  de SU document_type_code (o la "default" del proyecto si no hay una
  específica), no con un tipo único elegido para todo el lote.
- Reanudación: si una corrida anterior falló a la mitad, la siguiente
  corrida retoma exactamente donde quedó -- las fuentes que ya habían
  quedado exitosas se omiten (incrementalidad), y solo se reprocesan
  las que fallaron o son nuevas. No hace falta un mecanismo de
  "reanudar" aparte: es la misma regla de incrementalidad aplicada de
  nuevo.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


PER_SOURCE_DOCUMENT_TYPE = "por_fuente"
"""Valor de PipelineRun.document_type_code cuando cada fuente usó la
política de su propio document_type_code (Ronda 98, comportamiento por
defecto)."""


class PipelineItemStatus(str, Enum):
    EXITOSO = "exitoso"
    FALLIDO = "fallido"
    OMITIDO = "omitido"
    """Ni el archivo ni la configuración de procesamiento (política,
    metadatos heredados, fragmentos guardados) cambiaron desde la última
    corrida exitosa -- no se reprocesó, no es un error (ver `reason`)."""
    CANCELADO = "cancelado"


class PipelineRunStatus(str, Enum):
    EN_CURSO = "en_curso"
    COMPLETO = "completo"
    """Llegó al final y ningún item quedó en FALLIDO (pueden incluir
    EXITOSO y OMITIDO, nunca FALLIDO ni CANCELADO)."""
    COMPLETO_CON_ERRORES = "completo_con_errores"
    """Llegó al final, pero al menos un item quedó en FALLIDO."""
    CANCELADO = "cancelado"


class PipelineRunItem(BaseModel):
    """Resultado de procesar una fuente dentro de una corrida."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    source_title: str
    status: PipelineItemStatus
    content_hash: Optional[str] = None
    """Hash del archivo de la fuente al momento de procesarla (o de
    detectar que no había cambiado) -- None si no se pudo leer el
    archivo (se trata como "cambió", para forzar reprocesar y que el
    error real de lectura salga en `error`)."""
    steps_completed: list[str] = Field(default_factory=list)
    """Subconjunto ordenado de ["extraccion", "fragmentacion",
    "indexacion"] -- permite saber exactamente en qué paso se detuvo
    una fuente fallida, sin adivinar a partir del mensaje de error."""
    chunks_indexed: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    # --- Ronda 98: trazabilidad de la política y causa de la decisión.
    # Todos opcionales: las corridas guardadas antes de esta ronda no los
    # tienen (y por eso su siguiente corrida reprocesa, ver RunPipeline).
    document_type_code: Optional[str] = None
    """document_type_code de la fuente en el momento de procesarla."""
    policy_document_type_code: Optional[str] = None
    """De qué política salieron los parámetros: el mismo document_type_code
    (política específica), "default" (respaldo del proyecto) o None con
    policy_origin="interna" (parámetros por defecto de RAG Studio)."""
    policy_origin: Optional[str] = None
    """"especifica" | "default_proyecto" | "interna" | "forzada"."""
    policy_strategy: Optional[str] = None
    policy_hash: Optional[str] = None
    metadata_hash: Optional[str] = None
    """Huella de los metadatos que heredan los fragmentos de esta fuente."""
    chunks_digest: Optional[str] = None
    """Huella de los fragmentos guardados (texto, tipo, sección y
    metadatos heredados) al terminar -- detecta cambios hechos fuera del
    pipeline (p. ej. re-fragmentar a mano con otra política)."""
    reason: Optional[str] = None
    """Por qué se procesó u omitió la fuente, en texto para el operador."""


class PipelineRun(BaseModel):
    """Una corrida completa del pipeline sobre todas las fuentes de un
    proyecto. Se conserva el historial completo de corridas (a
    diferencia de ExtractionRecord/FragmentationPolicy/IndexInfo, que
    guardan solo el estado vigente) -- el documento maestro exige poder
    auditar corridas pasadas, no solo la última."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    document_type_code: str = "default"
    status: PipelineRunStatus = PipelineRunStatus.EN_CURSO
    items: list[PipelineRunItem] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    @property
    def has_critical_errors(self) -> bool:
        return any(item.status == PipelineItemStatus.FALLIDO for item in self.items)

    @property
    def is_usable_as_index_base(self) -> bool:
        """Compuerta 3 del documento maestro: "no usar una corrida
        incompleta como base de índice". Solo una corrida COMPLETO
        (llegó al final, sin fuentes fallidas) se considera una base
        confiable -- CANCELADO o COMPLETO_CON_ERRORES no lo son, aunque
        parte de sus fuentes sí se hayan indexado correctamente."""
        return self.status == PipelineRunStatus.COMPLETO
