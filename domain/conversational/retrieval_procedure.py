"""Ronda 106 (autorizada por NEXOM): procedimiento de recuperación del motor
conversacional, elegido por proyecto.

- "r105b": procedimiento anterior. Afinidad título-intención combinada por
  puesto (Ronda 102, C1) con los títulos de C2; configuración de reranking de
  la Ronda 105b (P1).
- "r106": V + Y + R, siempre juntos:
  - V (section_affinity.combine_by_value): la afinidad suma según su valor;
  - Y (section_affinity.affinity_title(exclude_yaml_only=True)): un fragmento
    solo-YAML no recibe afinidad;
  - R (reference_resolution): el contenido del documento referido por un
    fragmento puente queda por delante del puente.
  P1 (reranking) no cambia. V sin R reintroduce la regresión sintética de la
  Ronda 102, por eso no existen ajustes separados: el proyecto elige uno de
  los dos procedimientos completos.

Los tres componentes actúan solo en el reordenamiento conversacional, que
ocurre con filtro de metadatos aplicado (Ronda 91). Sin filtros, r106 entrega
exactamente lo mismo que r105b. Nunca cambian la intención, la confianza, las
variables, los filtros, los guardrails ni la decisión.

Persistencia: entrada versionada `retrieval_procedure` de la tabla
`configuration` del project.db (sin migración de esquema). Un proyecto sin
esa entrada -- todo proyecto creado antes de esta ronda, y toda instantánea
publicada antes -- usa r105b: su configuración efectiva no cambia en
silencio. Los proyectos nuevos se crean con r106.
"""
from __future__ import annotations

from typing import Optional

PROCEDURE_R105B = "r105b"
PROCEDURE_R106 = "r106"
SUPPORTED_PROCEDURES = (PROCEDURE_R105B, PROCEDURE_R106)
DEFAULT_FOR_NEW_PROJECTS = PROCEDURE_R106
DEFAULT_WITHOUT_SETTING = PROCEDURE_R105B
"""Proyectos e instantáneas sin ajuste guardado (anteriores a la Ronda 106)."""
CONFIGURATION_KEY = "retrieval_procedure"


class UnknownRetrievalProcedureError(ValueError):
    """El proyecto pide un procedimiento que este código no conoce (p. ej.
    una instantánea publicada con una versión más nueva de RAG Studio). Nunca
    se sustituye en silencio por otro."""


def validate_procedure(value: Optional[str]) -> str:
    """Valor efectivo: None -> r105b (sin ajuste); desconocido -> error."""
    if value is None or not str(value).strip():
        return DEFAULT_WITHOUT_SETTING
    valor = str(value).strip().lower()
    if valor not in SUPPORTED_PROCEDURES:
        raise UnknownRetrievalProcedureError(
            f"Procedimiento de recuperación desconocido: {value!r}. Esta versión de RAG Studio admite "
            f"{', '.join(SUPPORTED_PROCEDURES)}. Actualice RAG Studio o cambie el ajuste del proyecto."
        )
    return valor
