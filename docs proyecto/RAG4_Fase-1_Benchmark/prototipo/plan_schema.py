# -*- coding: utf-8 -*-
"""Esquema cerrado del plan de recuperación que el planificador LLM
(Sistema B) puede proponer -- RAG_STUDIO_Decision_RAG4_Excepcion_Controlada.docx,
sección 7: "Su salida debe cumplir un esquema cerrado (PlanDeRecuperacion)
con un catálogo autorizado de: retriever, query, filtros, top_k,
estrategia, hop y condición de continuación -- nada más." RAG STUDIO
valida este plan ANTES de ejecutar cualquier búsqueda real; el
planificador nunca ejecuta nada por sí mismo, solo propone.

Este archivo vive fuera del paquete `ragstudio` real (es el prototipo
aislado de la Fase -1, no un cambio de producto) pero se instala en el
mismo entorno virtual para poder importar `application.rag.service`.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

# Catálogo cerrado de retrievers autorizados -- el planificador solo
# puede elegir uno de estos nombres exactos. query_structured queda
# habilitado en el esquema para cuando el corpus SÍ tenga fuentes
# XLSX/CSV (ver limitación documentada en README.md de este directorio
# -- el piloto actual no tiene ninguna), pero cualquier plan que lo pida
# hoy fallará la validación de forma explícita, no en silencio.
class Retriever(str, Enum):
    HYBRID_SEARCH = "hybrid_search"
    QUERY_STRUCTURED = "query_structured"


class ContinuationCondition(str, Enum):
    CONTINUAR = "continuar"  # hace falta otro hop antes de responder
    FINAL = "final"  # este hop ya es suficiente para responder


class PlanStep(BaseModel):
    """Un solo paso (hop) del plan -- catálogo cerrado, ver docstring
    del módulo. Cualquier campo fuera de esta lista es rechazado por
    pydantic (model_config below) -- el planificador no puede colar
    instrucciones adicionales fingiendo ser parte del esquema."""

    model_config = {"extra": "forbid"}

    retriever: Retriever
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(ge=1, le=20)
    # "estrategia" es informativa (para el registro de auditoría), no
    # cambia el comportamiento real de hybrid_search -- las únicas
    # perillas reales de RagService.search_hybrid son rerank/
    # expand_to_parent, controladas aparte para no dejar que el
    # planificador invente parámetros que RagService no expone.
    estrategia: str = Field(max_length=200)
    rerank: bool = False
    expand_to_parent: bool = False
    hop: int = Field(ge=1, le=6)
    condicion_continuacion: ContinuationCondition
    razonamiento: str = Field(max_length=1000, description="Explicación breve del planificador para este paso -- solo auditoría, nunca se ejecuta como instrucción.")

    @field_validator("query")
    @classmethod
    def query_no_vacia(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query no puede quedar vacía tras strip()")
        return v.strip()


class PlanDeRecuperacion(BaseModel):
    """El plan completo que el planificador propone para UNA pregunta
    del corpus -- una lista ordenada de PlanStep, nunca más de
    max_hops (ver Sistema B). RAG STUDIO ejecuta paso a paso, deteniéndose
    en el primer paso con condicion_continuacion == FINAL o al agotar
    max_hops, lo que ocurra primero."""

    model_config = {"extra": "forbid"}

    pasos: list[PlanStep] = Field(min_length=1, max_length=6)
