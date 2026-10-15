"""NEXOM Knowledge Package v1.0.0 vendorizado (RAG-INC-01c).

`v1_0_0/` contiene copias BYTE A BYTE de los artefactos firmados; no se
editan. Su lista, el hash esperado de cada uno y su origen están en
`VENDORIZADO_v1_0_0.json` (la prueba tests/unit/contracts/test_vendored_contract.py
falla ante cualquier diferencia):

- normativos (Declaración de aceptación v1.0.0 §4.1): 14 schemas,
  `common/id_scheme.py`, `validator/validate_knowledge_package.py`;
- reproducibilidad y QA (§4.2): `requirements.lock.txt`,
  `validator/test_negative_cases.py`;
- fixture oficial del ejemplo 1.0.0: `example_package/`, `delivery/` y el ZIP.

Este módulo solo localiza y carga esos archivos; no contiene lógica del
contrato. Los módulos firmados se cargan desde su ubicación tal cual: el
validador hace `sys.path.insert(0, <v1_0_0>/common)` e `import id_scheme`
(comportamiento propio del artefacto firmado, que no se modifica).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

V1_0_0_DIR = Path(__file__).resolve().parent / "v1_0_0"
SCHEMAS_DIR = V1_0_0_DIR / "schemas"
ID_SCHEME_PATH = V1_0_0_DIR / "common" / "id_scheme.py"
VALIDATOR_PATH = V1_0_0_DIR / "validator" / "validate_knowledge_package.py"
VENDORED_INDEX = Path(__file__).resolve().parent / "VENDORIZADO_v1_0_0.json"

_CACHE: dict[str, ModuleType] = {}


def _cargar(nombre: str, ruta: Path) -> ModuleType:
    if nombre in _CACHE:
        return _CACHE[nombre]
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    if spec is None or spec.loader is None:  # pragma: no cover - archivo vendorizado ausente
        raise ImportError(f"No se pudo cargar el artefacto vendorizado {ruta}")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    _CACHE[nombre] = modulo
    return modulo


def load_id_scheme() -> ModuleType:
    """`common/id_scheme.py` firmado (fórmulas normativas de identidad,
    canonicalización RFC 8785 y `content_digest`)."""
    return _cargar("nexom_kp_v1_0_0_id_scheme", ID_SCHEME_PATH)


def load_validator() -> ModuleType:
    """`validator/validate_knowledge_package.py` firmado."""
    return _cargar("nexom_kp_v1_0_0_validator", VALIDATOR_PATH)
