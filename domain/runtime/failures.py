"""Diagnóstico de turnos FALLIDOS del runtime (Ronda 93, 2026-10-06,
SOLICITUD COMPLEMENTARIA NEXOM "Caso failed": un caso con
Resultado=failed, Categoría de error="—" y Trace ID presente).

Causa raíz del lado de RAG STUDIO: cuando el motor conversacional
lanzaba una excepción al atender `POST /projects/{id}/messages`, el
servicio respondía `500 Internal Server Error` en texto plano -- sin
categoría, etapa, código, mensaje ni identificador -- y el turno no se
guardaba en runtime.db (solo se guardaban los turnos exitosos). El
consumidor (NEXOM Testing Agent) solo podía marcar "failed" sin causa, y
ni la pestaña Monitoreo ni el registro permitían correlacionarlo.

Este módulo es puro: define el vocabulario. La clasificación a partir de
una excepción real vive en application.runtime.failure_diagnosis.

Taxonomía (nombres de la solicitud, sección "Categorías de referencia",
más `snapshot_error` y `storage_error`, propias de la arquitectura de
RAG STUDIO). `unclassified` solo se usa cuando no hay ninguna evidencia
para clasificar; nunca se deja la categoría vacía.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class FailureCategory(str, Enum):
    RETRIEVAL = "retrieval_error"
    """Búsqueda en el índice vectorial/léxico (p. ej. índice bloqueado o dañado)."""
    EMBEDDING = "embedding_error"
    """Modelo de embeddings: carga, descarga o cálculo del vector de la consulta."""
    LLM = "llm_error"
    """Reservada: el runtime de RAG STUDIO no genera lenguaje natural (no la emite hoy)."""
    TIMEOUT = "timeout"
    CONFIGURATION = "configuration_error"
    """Configuración del proyecto o del despliegue (dato inválido, instantánea inexistente)."""
    SNAPSHOT = "snapshot_error"
    """La instantánea publicada no se pudo cargar (archivos faltantes o ilegibles)."""
    GUARDRAIL = "guardrail_error"
    """Evaluación de reglas (guardrails) o canalización."""
    INTENT = "intent_error"
    """Detección de intención o de variables."""
    SOURCE = "source_error"
    """Metadatos/fuentes usados para filtrar la recuperación."""
    STORAGE = "storage_error"
    """Base de datos local (project.db de la instantánea o runtime.db)."""
    INFRASTRUCTURE = "infrastructure_error"
    """Recursos del sistema (memoria, disco, permisos)."""
    EVALUATION = "evaluation_error"
    """Evaluador del banco de pruebas (solo en Calidad, no en el runtime)."""
    UNEXPECTED = "unexpected_exception"
    """Excepción real, con traza, en un componente sin categoría más específica."""
    UNCLASSIFIED = "unclassified"
    """Sin evidencia suficiente para clasificar (p. ej. excepción sin traza)."""


class FailureStage(str, Enum):
    CARGA_INSTANTANEA = "carga_instantanea"
    EMBEDDINGS_CONSULTA = "embeddings_consulta"
    DETECCION_INTENCION = "deteccion_intencion"
    DETECCION_VARIABLES = "deteccion_variables"
    FILTRADO_METADATOS = "filtrado_metadatos"
    BUSQUEDA = "busqueda"
    REORDENAMIENTO = "reordenamiento"
    GUARDRAILS = "guardrails"
    REGISTRO_BITACORA = "registro_bitacora"
    EVALUACION = "evaluacion"
    MOTOR_CONVERSACIONAL = "motor_conversacional"
    """Dentro del motor, sin un componente más específico identificable."""
    DESCONOCIDA = "desconocida"


class FailureDiagnosis(BaseModel):
    """Diagnóstico persistible de un fallo. `technical_detail` lleva el
    tipo y mensaje de la excepción y la cadena de llamadas (módulo:función:
    línea), nunca valores de variables ni secretos."""

    category: FailureCategory
    stage: FailureStage
    code: str
    """Identificador estable y corto (p. ej. "embedding.model_unavailable")."""
    summary: str
    """Mensaje resumido para operación, en español."""
    exception_type: Optional[str] = None
    technical_detail: Optional[str] = None
