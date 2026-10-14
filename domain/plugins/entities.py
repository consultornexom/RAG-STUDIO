"""Entidades del contexto Complementos (Etapa 8: extensibilidad).

RAG STUDIO.odt es explícito en que la primera versión "no debería
intentar cubrir todos los conectores y modelos posibles": los
conectores empresariales, modelos adicionales y canalizaciones reales
"pueden agregarse posteriormente mediante complementos". El propio
documento enumera 4 tipos de complemento bajo ese título: Plantillas,
Nuevos proveedores, Importadores, Evaluadores personalizados -- ese es
el vocabulario exacto que sigue `PluginKind`.

A diferencia de todos los contextos anteriores (Etapas 2-7, que viven
en el `project.db` de cada proyecto), el registro de complementos es
GLOBAL: vive en `application.db`, junto al índice de proyectos (ver
`infrastructure/database/models.py`, docstring de `GlobalBase`: "índice
ligero de proyectos, preferencias, plantillas, catálogos reutilizables
-- el resto se añade cuando exista su caso de uso"). Un complemento no
pertenece a un proyecto: está disponible para cualquier proyecto de la
instalación, igual que un modelo de embeddings instalado."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PluginKind(str, Enum):
    """Los 4 tipos de complemento del documento maestro."""

    PLANTILLA = "plantilla"
    """Una configuración inicial reutilizable para proyectos nuevos
    (p. ej. esquema de metadatos y políticas de fragmentación
    sugeridas para un sector). Es solo datos (`config`), no código: no
    necesita `entry_point`."""
    PROVEEDOR = "proveedor"
    """Un nuevo proveedor de embeddings (o, a futuro, de LLM) --
    `entry_point` debe resolver a una subclase concreta de
    `domain.rag.ports.EmbeddingProvider`."""
    IMPORTADOR = "importador"
    """Un nuevo extractor de texto para un tipo de fuente no cubierto
    todavía (XLSX, CSV, HTML, JSON, XML...) -- `entry_point` debe
    resolver a una subclase concreta de
    `domain.ingestion.ports.TextExtractor`."""
    EVALUADOR = "evaluador"
    """Un criterio de evaluación personalizado para el banco de
    pruebas de Etapa 6, más allá de lo que compara `RunEvaluation` por
    defecto -- `entry_point` debe resolver a una subclase concreta de
    `domain.plugins.ports.CustomEvaluator`."""


_KINDS_REQUIRING_ENTRY_POINT = {PluginKind.PROVEEDOR, PluginKind.IMPORTADOR, PluginKind.EVALUADOR}

# Ítem 2 de la segunda evaluación de madurez post-8-etapas (ver
# bitácora): antes, `Plugin.config` viajaba siempre en texto plano en
# `application.db`, incluida una posible API key de un proveedor
# externo real (ADR-001, sección 12, exige que ninguna credencial viaje
# en texto plano). No hay forma de saber en general si un valor de
# `config` es sensible -- es JSON arbitrario -- así que se usa una
# convención de nombre de clave (mismo criterio ya usado por
# `app.logging_setup.RedactSensitiveDataFilter` para redactar logs):
# cualquier clave cuyo nombre contenga alguno de estos fragmentos
# (sin distinguir mayúsculas) se trata como sensible y se intenta
# guardar en el almacén seguro de credenciales del sistema operativo en
# vez de en la base de datos (ver `application.plugins.commands.
# register_plugin` y `infrastructure.security.keyring_credential_store`).
_SENSITIVE_CONFIG_KEY_MARKERS = ("key", "secret", "token", "password", "credential", "contraseña")

CREDENTIAL_STORE_PLACEHOLDER = "__guardado_en_almacen_seguro__"
"""Valor que reemplaza, dentro de `Plugin.config` tal como se persiste
en `application.db`, a un valor sensible que sí se guardó con éxito en
el almacén seguro del sistema operativo -- así queda claro que el campo
tiene un valor configurado, sin exponerlo en texto plano."""


def is_sensitive_config_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_CONFIG_KEY_MARKERS)


def credential_key(code: str, config_key: str) -> str:
    """Clave estable bajo la que un valor sensible de `config` se
    guarda en `CredentialStore`, a partir del `code` del complemento
    (único por tipo) y el nombre del campo de config -- misma clave
    tanto al guardar (`RegisterPlugin`) como al resolver de vuelta
    (`PluginService.resolve_config`)."""
    return f"plugin:{code}:{config_key}"


class Plugin(BaseModel):
    """Un complemento registrado en la instalación.

    `entry_point` sigue la convención estándar de Python para puntos
    de entrada: `"paquete.modulo:NombreDeClase"`. Es obligatorio para
    los 3 tipos que cargan código (proveedor/importador/evaluador);
    una plantilla es solo datos en `config`, sin código que cargar."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: PluginKind
    code: str
    """Identificador legible único dentro de su tipo (p. ej.
    "proveedor_openai_embeddings"), no el `id` interno."""
    name: str
    description: str = ""
    version: str = "0.1.0"
    entry_point: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    """Configuración arbitraria en JSON: para una plantilla, son los
    valores por defecto que ofrece: para un proveedor/importador/
    evaluador, son parámetros que su implementación puede leer al
    construirse (p. ej. una API key -- ver "Limitaciones conocidas" en
    README sobre el manejo de secretos, todavía no resuelto aquí)."""
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("code")
    @classmethod
    def _code_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("code no puede estar vacío")
        return v

    @field_validator("entry_point")
    @classmethod
    def _entry_point_formato(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if ":" not in v:
            raise ValueError(
                f"entry_point {v!r} no sigue el formato 'paquete.modulo:NombreDeClase'"
            )
        return v

    @property
    def requires_entry_point(self) -> bool:
        return self.kind in _KINDS_REQUIRING_ENTRY_POINT
