"""Clasificación determinista de una excepción real en un
`FailureDiagnosis` (Ronda 93, ver domain.runtime.failures).

Cómo se clasifica -- sin listas de mensajes ni casos particulares:
1. Por el TIPO de excepción cuando es inequívoco (TimeoutError ->
   timeout; MemoryError o disco lleno -> infrastructure_error).
2. Por la CADENA DE LLAMADAS real (traceback): el componente más profundo
   reconocible indica la categoría (p. ej. una excepción que nace dentro
   de fastembed o de infrastructure.embeddings es embedding_error) y la
   función de la capa de aplicación más profunda indica la etapa (p. ej.
   `SimulateConversation._search_and_filter` -> busqueda).
3. Si hay traza pero ningún componente reconocible: unexpected_exception.
   Solo sin traza alguna: unclassified. Nunca queda vacía.

El mismo diagnóstico, para la misma excepción, da siempre el mismo
resultado (CA-FAIL-08: reconstruible de forma determinista).
"""
from __future__ import annotations

import errno
import sqlite3
import traceback
from types import TracebackType
from typing import Optional

from domain.rag.exceptions import RerankingRequiredUnavailableError
from domain.runtime.failures import FailureCategory, FailureDiagnosis, FailureStage

# (prefijo de módulo, categoría, etapa por defecto si ningún marco de la
# capa de aplicación da una más precisa). Se evalúan del marco más
# profundo hacia afuera; gana el primer marco reconocido.
_COMPONENTES: tuple[tuple[str, FailureCategory, FailureStage], ...] = (
    ("fastembed", FailureCategory.EMBEDDING, FailureStage.EMBEDDINGS_CONSULTA),
    ("onnxruntime", FailureCategory.EMBEDDING, FailureStage.EMBEDDINGS_CONSULTA),
    ("huggingface_hub", FailureCategory.EMBEDDING, FailureStage.EMBEDDINGS_CONSULTA),
    ("infrastructure.embeddings", FailureCategory.EMBEDDING, FailureStage.EMBEDDINGS_CONSULTA),
    ("infrastructure.rerankers", FailureCategory.RETRIEVAL, FailureStage.REORDENAMIENTO),
    ("qdrant_client", FailureCategory.RETRIEVAL, FailureStage.BUSQUEDA),
    ("infrastructure.vectorstores", FailureCategory.RETRIEVAL, FailureStage.BUSQUEDA),
    ("infrastructure.llm", FailureCategory.LLM, FailureStage.MOTOR_CONVERSACIONAL),
    ("sqlalchemy", FailureCategory.STORAGE, FailureStage.MOTOR_CONVERSACIONAL),
    ("sqlite3", FailureCategory.STORAGE, FailureStage.MOTOR_CONVERSACIONAL),
    ("alembic", FailureCategory.STORAGE, FailureStage.CARGA_INSTANTANEA),
    ("infrastructure.database.metadata_repositories", FailureCategory.SOURCE, FailureStage.FILTRADO_METADATOS),
    ("infrastructure.database.document_repositories", FailureCategory.SOURCE, FailureStage.FILTRADO_METADATOS),
    ("infrastructure.database.runtime_repositories", FailureCategory.STORAGE, FailureStage.REGISTRO_BITACORA),
    ("infrastructure.database", FailureCategory.STORAGE, FailureStage.MOTOR_CONVERSACIONAL),
    ("domain.conversational.intent_matching", FailureCategory.INTENT, FailureStage.DETECCION_INTENCION),
    ("domain.conversational.variable_extraction", FailureCategory.INTENT, FailureStage.DETECCION_VARIABLES),
    ("domain.conversational.rule_evaluation", FailureCategory.GUARDRAIL, FailureStage.GUARDRAILS),
    ("domain.conversational.section_affinity", FailureCategory.RETRIEVAL, FailureStage.REORDENAMIENTO),
    ("application.rag", FailureCategory.RETRIEVAL, FailureStage.BUSQUEDA),
    ("domain.rag", FailureCategory.RETRIEVAL, FailureStage.BUSQUEDA),
    ("interfaces.api.runtime_context", FailureCategory.SNAPSHOT, FailureStage.CARGA_INSTANTANEA),
)

# Etapa según la función de la capa de aplicación/runtime en curso.
_ETAPAS_POR_FUNCION: dict[str, FailureStage] = {
    "_search_and_filter": FailureStage.BUSQUEDA,
    "_query_structured": FailureStage.BUSQUEDA,
    "_matches_all_filters": FailureStage.FILTRADO_METADATOS,
    "_source_matches_filters": FailureStage.FILTRADO_METADATOS,
    "_source_value_matches": FailureStage.FILTRADO_METADATOS,
    "_empty_filter_hint": FailureStage.FILTRADO_METADATOS,
    "_embed_reference_texts": FailureStage.DETECCION_INTENCION,
    "_catalog_mention_masker": FailureStage.DETECCION_VARIABLES,
    "_candidates_for_field": FailureStage.DETECCION_VARIABLES,
    "_detect_variables": FailureStage.DETECCION_VARIABLES,
    "_retrieval_query": FailureStage.DETECCION_VARIABLES,
    "match_intent": FailureStage.DETECCION_INTENCION,
    "embed_query": FailureStage.EMBEDDINGS_CONSULTA,
    "_build": FailureStage.CARGA_INSTANTANEA,
    "get_latest": FailureStage.CARGA_INSTANTANEA,
}
_MODULOS_DE_ETAPA = ("application.", "domain.", "interfaces.api.")

_ETAPA_LEGIBLE = {
    FailureStage.CARGA_INSTANTANEA: "la carga de la instantánea",
    FailureStage.EMBEDDINGS_CONSULTA: "el cálculo de embeddings de la consulta",
    FailureStage.DETECCION_INTENCION: "la detección de intención",
    FailureStage.DETECCION_VARIABLES: "la detección de variables",
    FailureStage.FILTRADO_METADATOS: "el filtrado por metadatos",
    FailureStage.BUSQUEDA: "la búsqueda de fragmentos",
    FailureStage.REORDENAMIENTO: "el reordenamiento de fragmentos",
    FailureStage.GUARDRAILS: "la evaluación de guardrails",
    FailureStage.REGISTRO_BITACORA: "el registro en la bitácora",
    FailureStage.EVALUACION: "la evaluación del caso",
    FailureStage.MOTOR_CONVERSACIONAL: "el motor conversacional",
    FailureStage.DESCONOCIDA: "una etapa no identificada",
}

_MAX_MARCOS = 15
_MAX_MENSAJE = 240


def _marcos(tb: Optional[TracebackType]) -> list[tuple[str, str, int]]:
    """(módulo, función, línea) de cada marco, del más externo al más profundo."""
    marcos: list[tuple[str, str, int]] = []
    while tb is not None:
        frame = tb.tb_frame
        modulo = str(frame.f_globals.get("__name__", "?"))
        marcos.append((modulo, frame.f_code.co_name, tb.tb_lineno))
        tb = tb.tb_next
    return marcos


def _cadena_de_excepciones(exc: BaseException) -> list[BaseException]:
    """La excepción y sus causas (`raise ... from`), de la exterior a la raíz."""
    cadena: list[BaseException] = []
    actual: Optional[BaseException] = exc
    while actual is not None and actual not in cadena:
        cadena.append(actual)
        actual = actual.__cause__ or (None if actual.__suppress_context__ else actual.__context__)
    return cadena


def _primera_linea(texto: str) -> str:
    linea = (texto or "").strip().splitlines()[0] if (texto or "").strip() else ""
    return linea if len(linea) <= _MAX_MENSAJE else linea[: _MAX_MENSAJE - 1] + "…"


def diagnose_exception(
    exc: BaseException, default_stage: FailureStage = FailureStage.DESCONOCIDA,
) -> FailureDiagnosis:
    cadena = _cadena_de_excepciones(exc)
    marcos: list[tuple[str, str, int]] = []
    for eslabon in cadena:  # de la excepción exterior a la causa raíz: la raíz queda al final (más profunda)
        marcos.extend(_marcos(eslabon.__traceback__))
    raiz = cadena[-1]

    categoria: Optional[FailureCategory] = None
    etapa: Optional[FailureStage] = None
    for modulo, _funcion, _linea in reversed(marcos):
        for prefijo, cat, etapa_defecto in _COMPONENTES:
            if modulo == prefijo or modulo.startswith(prefijo + "."):
                categoria, etapa = cat, etapa_defecto
                break
        if categoria is not None:
            break
    for modulo, funcion, _linea in reversed(marcos):
        if funcion in _ETAPAS_POR_FUNCION and modulo.startswith(_MODULOS_DE_ETAPA):
            # La función de aplicación precisa la etapa salvo que el
            # componente ya sea la carga de la instantánea.
            if etapa != FailureStage.CARGA_INSTANTANEA or _ETAPAS_POR_FUNCION[funcion] == FailureStage.CARGA_INSTANTANEA:
                etapa = _ETAPAS_POR_FUNCION[funcion]
            break

    codigo_especifico: Optional[str] = None
    texto_raiz = str(raiz)
    requerido = next((e for e in cadena if isinstance(e, RerankingRequiredUnavailableError)), None)
    if requerido is not None:
        # Ronda 105b (P1): el proyecto exige reranking y el modelo no está
        # disponible -- error de configuración del despliegue, explícito. El
        # resumen usa el mensaje de configuración (qué hacer), no la causa
        # técnica, que queda en el detalle.
        categoria, codigo_especifico = FailureCategory.CONFIGURATION, "configuration.reranking_unavailable"
        texto_raiz = str(requerido)
    elif any(isinstance(e, TimeoutError) for e in cadena):
        categoria, codigo_especifico = FailureCategory.TIMEOUT, "timeout"
    elif any(isinstance(e, MemoryError) for e in cadena):
        categoria, codigo_especifico = FailureCategory.INFRASTRUCTURE, "infrastructure.out_of_memory"
    elif any(isinstance(e, OSError) and e.errno == errno.ENOSPC for e in cadena):
        categoria, codigo_especifico = FailureCategory.INFRASTRUCTURE, "infrastructure.disk_full"
    elif any(isinstance(e, PermissionError) for e in cadena):
        categoria, codigo_especifico = FailureCategory.INFRASTRUCTURE, "infrastructure.permission_denied"
    elif any(isinstance(e, sqlite3.OperationalError) and "locked" in str(e).lower() for e in cadena) or (
        categoria == FailureCategory.STORAGE and "database is locked" in texto_raiz.lower()
    ):
        categoria, codigo_especifico = FailureCategory.STORAGE, "storage.database_locked"
    elif categoria == FailureCategory.RETRIEVAL and "already accessed by another instance" in texto_raiz:
        codigo_especifico = "retrieval.index_locked"
    elif categoria == FailureCategory.SNAPSHOT and isinstance(raiz, FileNotFoundError):
        codigo_especifico = "snapshot.file_missing"

    if categoria is None:
        categoria = FailureCategory.UNEXPECTED if marcos else FailureCategory.UNCLASSIFIED
    if etapa is None:
        etapa = default_stage

    tipo = type(raiz).__name__
    codigo = codigo_especifico or f"{categoria.value.removesuffix('_error')}.{tipo}"
    resumen = f"Falló {_ETAPA_LEGIBLE[etapa]} ({categoria.value}): {_primera_linea(texto_raiz) or tipo}"
    lineas = [f"{type(e).__name__}: {_primera_linea(str(e))}" for e in cadena]
    lineas += [f"  {m}:{f}:{n}" for m, f, n in marcos[-_MAX_MARCOS:]]
    return FailureDiagnosis(
        category=categoria, stage=etapa, code=codigo, summary=resumen,
        exception_type=tipo, technical_detail="\n".join(lineas),
    )


def format_traceback(exc: BaseException) -> str:
    """Traza completa para el registro operativo (ragstudio-api.log)."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def format_evaluation_error(diagnosis: FailureDiagnosis) -> str:
    """Texto persistido en `EvaluationResultItem.error` (Calidad) -- nunca
    vacío: categoría, etapa y código entre corchetes, el resumen y el
    detalle técnico. Se guarda en la columna de texto ya existente: no
    requiere migración de project.db."""
    texto = (
        f"[categoría={diagnosis.category.value} · etapa={diagnosis.stage.value} · "
        f"código={diagnosis.code}] {diagnosis.summary}"
    )
    if diagnosis.technical_detail:
        texto += "\n" + diagnosis.technical_detail
    return texto
