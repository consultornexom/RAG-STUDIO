"""Carga dinámica de complementos a partir de su `entry_point`
("paquete.modulo:NombreDeClase") -- el "contrato SDK" mínimo de Etapa
8: cómo la aplicación localiza el código de un complemento instalado.

Vive en `domain` (no en `infrastructure`) porque solo usa `importlib`
de la biblioteca estándar (ADR-001: domain puede depender de stdlib +
Pydantic) y no hay ningún adaptador alternativo que intercambiar --a
diferencia de `EmbeddingProvider`/`VectorStore`/`TextExtractor`, que sí
tienen implementaciones concretas intercambiables en infrastructure,
"cómo se importa un módulo de Python" es siempre lo mismo. Mantenerlo
aquí evita un puerto con una sola implementación posible, sin
beneficio real de indirección."""
from __future__ import annotations

import importlib

from .entities import Plugin, PluginKind
from .exceptions import PluginLoadError
from .ports import CustomEvaluator

_CONTRACT_BY_KIND: dict[PluginKind, str] = {
    PluginKind.PROVEEDOR: "domain.rag.ports.EmbeddingProvider",
    PluginKind.IMPORTADOR: "domain.ingestion.ports.TextExtractor",
    PluginKind.EVALUADOR: "domain.plugins.ports.CustomEvaluator",
}
"""Solo para mensajes de error legibles -- la validación real
(`_expected_base_class`) importa la clase real, no compara strings."""


def expected_contract_label(kind: PluginKind) -> str:
    """Nombre legible ("paquete.modulo.Clase") del contrato que debe
    implementar un complemento de este tipo -- usado para mostrarle al
    usuario qué se espera al registrar/validar un complemento (una
    plantilla no tiene contrato de código)."""
    return _CONTRACT_BY_KIND.get(kind, "(sin contrato de código -- es solo datos)")


def _expected_base_class(kind: PluginKind):
    if kind == PluginKind.PROVEEDOR:
        from domain.rag.ports import EmbeddingProvider
        return EmbeddingProvider
    if kind == PluginKind.IMPORTADOR:
        from domain.ingestion.ports import TextExtractor
        return TextExtractor
    if kind == PluginKind.EVALUADOR:
        return CustomEvaluator
    return None


def load_entry_point(entry_point: str) -> type:
    """Resuelve "paquete.modulo:NombreDeClase" a la clase real.

    Lanza `PluginLoadError` (nunca `ImportError`/`AttributeError`
    crudos) si el módulo no existe, o si el módulo existe pero no
    define ese nombre -- mismo criterio del resto del proyecto de
    convertir errores técnicos crudos en errores de dominio legibles
    (ver p. ej. `CatalogRequiredForFieldTypeError`)."""
    if ":" not in entry_point:
        raise PluginLoadError(entry_point, "formato inválido, se espera 'paquete.modulo:NombreDeClase'")
    module_path, _, class_name = entry_point.partition(":")
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001 - cualquier falla de import se reporta igual
        raise PluginLoadError(entry_point, f"no se pudo importar el módulo {module_path!r}: {exc}") from exc
    try:
        obj = getattr(module, class_name)
    except AttributeError as exc:
        raise PluginLoadError(
            entry_point, f"el módulo {module_path!r} no define {class_name!r}"
        ) from exc
    if not isinstance(obj, type):
        raise PluginLoadError(entry_point, f"{class_name!r} no es una clase")
    return obj


def load_and_validate(plugin: Plugin) -> type:
    """Carga el `entry_point` del complemento y valida que la clase
    obtenida en verdad implemente el contrato esperado para su tipo
    (subclase concreta del puerto correspondiente). Una plantilla no
    tiene contrato de código: si se le pide validar sin entry_point,
    se considera válida (es solo datos)."""
    if plugin.entry_point is None:
        if plugin.requires_entry_point:
            raise PluginLoadError("(sin entry_point)", "este tipo de complemento necesita entry_point")
        return type(None)
    obj = load_entry_point(plugin.entry_point)
    expected = _expected_base_class(plugin.kind)
    if expected is not None and not (isinstance(obj, type) and issubclass(obj, expected)):
        raise PluginLoadError(
            plugin.entry_point,
            f"{obj.__name__!r} no implementa {expected.__module__}.{expected.__name__}",
        )
    return obj
