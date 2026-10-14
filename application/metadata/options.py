"""Vocabularios que la UI necesita para construir formularios, sin
tener que importar domain directamente (ADR-001, sección 4)."""
from __future__ import annotations

from domain.metadata.entities import CATALOG_BACKED_TYPES, FieldDataType

FIELD_DATA_TYPE_OPTIONS: list[str] = [t.value for t in FieldDataType]
CATALOG_BACKED_TYPE_VALUES: frozenset[str] = frozenset(t.value for t in CATALOG_BACKED_TYPES)

# Hallazgo real de validación visual: en "Valores por fuente" no
# quedaba claro qué formato se esperaba en el campo "Valor" para los
# tipos que no usan catálogo (texto libre) -- el usuario solo veía un
# campo genérico. Este mapeo se consulta desde la UI para mostrar una
# pista explícita del formato esperado según el tipo de dato del
# campo seleccionado, en vez de dejarlo implícito.
FIELD_DATA_TYPE_VALUE_HINTS: dict[str, str] = {
    FieldDataType.TEXTO.value: "Texto libre.",
    FieldDataType.TEXTO_LARGO.value: "Texto libre (puede ser extenso).",
    FieldDataType.NUMERO.value: "Número entero, ej. 42.",
    FieldDataType.DECIMAL.value: "Número decimal (usa punto), ej. 3.14.",
    FieldDataType.FECHA.value: "Fecha (AAAA-MM-DD), ej. 2026-08-03.",
    FieldDataType.FECHA_HORA.value: "Fecha y hora (AAAA-MM-DDTHH:MM), ej. 2026-08-03T09:30.",
    FieldDataType.BOOLEANO.value: "true o false.",
    FieldDataType.URL.value: "URL completa, ej. https://ejemplo.mx/pagina.",
    FieldDataType.IDENTIFICADOR.value: "Identificador o código único.",
    FieldDataType.NIVEL_SEGURIDAD.value: "Nivel de seguridad (texto libre acordado con el proyecto).",
    FieldDataType.ESTADO.value: "Estado (texto libre acordado con el proyecto).",
    FieldDataType.RELACION.value: "Identificador de la fuente/entidad relacionada.",
}
