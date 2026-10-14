"""Vocabularios del contexto Complementos expuestos a la UI (ADR-001:
la UI nunca importa domain directamente)."""
from __future__ import annotations

from domain.plugins.entities import PluginKind
from domain.plugins.loader import expected_contract_label

PLUGIN_KIND_OPTIONS = [kind.value for kind in PluginKind]


def plugin_kind_contract_label(kind: str) -> str:
    """Reexpone `expected_contract_label` aceptando un string plano
    (la UI nunca importa `PluginKind` directamente)."""
    return expected_contract_label(PluginKind(kind))
