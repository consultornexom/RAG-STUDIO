"""Configuración del runtime validada ANTES de arrancar (Ronda 92,
2026-10-06, hallazgo real de usuario al desplegar un paquete de entrega).

Hallazgos que corrige:

1. `RAGSTUDIO_SNAPSHOT_VERSION` tenía un valor por defecto silencioso
   (1). Con una instantánea v2 el runtime se presentaba como v1 y los
   consumidores posteriores rechazaban la identidad de recuperación.
   Ahora la versión se DERIVA de la propia instantánea
   (`instantanea/snapshot_identity.json`, o el `manifest.json` del
   paquete de entrega que la contiene). Si se define la variable, debe
   coincidir. Si no se puede derivar y no se define, el proceso no arranca.
2. El nombre de la clave no era uniforme entre documentos
   (`RAG_API_KEY` frente a `RAGSTUDIO_API_KEY`). El nombre oficial es
   `RAGSTUDIO_API_KEY`; `RAG_API_KEY` se acepta solo como alias
   heredado, con aviso en el registro, y si ambos están definidos con
   valores distintos el proceso no arranca.
3. Validación previa completa: la carpeta de la instantánea existe, es
   la carpeta `instantanea/` (no la raíz del paquete), contiene un
   `project.db` válido, la versión declarada coincide, el perfil de
   embeddings corresponde al modelo con que se construyó el índice y los
   valores numéricos son válidos. TODOS los problemas se reportan juntos.

`python -m interfaces.api.check_config` ejecuta exactamente esta misma
validación sin arrancar el servicio (útil antes de `uvicorn`).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from infrastructure.embeddings.fastembed_provider import (
    AVAILABLE_EMBEDDING_PROFILES,
    EMBEDDING_MODEL_BY_PROFILE,
)
from infrastructure.filesystem.snapshot_identity import (
    IDENTITY_FILENAME,
    SnapshotIdentity,
    SnapshotIdentityError,
    content_fingerprint,
    read_project_db_facts,
    read_snapshot_identity,
)

logger = logging.getLogger(__name__)

API_KEY_VAR = "RAGSTUDIO_API_KEY"
LEGACY_API_KEY_VARS = ("RAG_API_KEY",)
SNAPSHOT_DIR_VAR = "RAGSTUDIO_SNAPSHOT_DIR"
SNAPSHOT_VERSION_VAR = "RAGSTUDIO_SNAPSHOT_VERSION"
HOME_VAR = "RAGSTUDIO_HOME"
PROFILE_VAR = "RAGSTUDIO_EMBEDDING_PROFILE"
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_PROFILE_BY_MODEL = {model: profile for profile, model in EMBEDDING_MODEL_BY_PROFILE.items()}


class RuntimeConfigurationError(RuntimeError):
    """La configuración no permite arrancar. `problems` trae cada causa
    por separado; el mensaje las enumera todas."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        detalle = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(
            "El runtime de RAG STUDIO no puede arrancar; corrige lo siguiente "
            f"(ver GUIA_DESPLIEGUE.md, sección 3):\n{detalle}"
        )


@dataclass(frozen=True)
class PinnedSnapshot:
    directory: Path
    project_id: str
    version: int
    version_source: str
    """De dónde salió la versión: snapshot_identity.json, manifest.json
    del paquete o la variable de entorno (instantáneas antiguas)."""
    embedding_model: Optional[str] = None
    content_fingerprint: Optional[str] = None


@dataclass(frozen=True)
class RuntimeConfig:
    installation_dir: str
    api_key: str
    embedding_profile: str
    embedding_profile_source: str
    log_level: str = "INFO"
    runtime_db_path: Optional[str] = None
    allowed_origins: Optional[list[str]] = None
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None
    pinned: Optional[PinnedSnapshot] = None
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        """Resumen sin secretos (para el registro y check_config)."""
        lineas = [
            f"modo de instantánea: {'fija' if self.pinned else 'registro de la instalación'}",
        ]
        if self.pinned:
            lineas += [
                f"carpeta de la instantánea: {self.pinned.directory}",
                f"proyecto: {self.pinned.project_id}",
                f"versión: {self.pinned.version} (tomada de {self.pinned.version_source})",
                f"modelo del índice: {self.pinned.embedding_model or 'no registrado'}",
            ]
        lineas += [
            f"perfil de embeddings: {self.embedding_profile} ({self.embedding_profile_source})",
            f"RAGSTUDIO_HOME (registro, runtime.db, modelos): {self.installation_dir}",
            f"runtime.db: {self.runtime_db_path or Path(self.installation_dir) / 'runtime.db'}",
            f"clave operativa: definida ({len(self.api_key)} caracteres)",
            f"nivel de registro: {self.log_level}",
            f"CORS: {', '.join(self.allowed_origins) if self.allowed_origins else 'desactivado'}",
            f"límite por minuto: {self.rate_limit_per_minute or 'sin límite'}",
        ]
        return lineas


def _limpio(env: Mapping[str, str], name: str) -> Optional[str]:
    valor = env.get(name)
    if valor is None:
        return None
    valor = valor.strip()
    return valor or None


def _manifest_del_paquete(snapshot_dir: Path) -> Optional[SnapshotIdentity]:
    """Paquetes de entrega exportados antes de la Ronda 92: la versión solo
    está en el manifest.json de la raíz del paquete (carpeta padre de
    `instantanea/`)."""
    manifest = snapshot_dir.parent / "manifest.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("instantanea_incluida"):
        return None
    version = data.get("snapshot_version")
    project_id = data.get("project_id")
    if not isinstance(version, int) or isinstance(version, bool) or not isinstance(project_id, str):
        return None
    return SnapshotIdentity(project_id=project_id, snapshot_version=version)


def resolve_pinned_snapshot(
    snapshot_dir: str | Path, declared_version: Optional[str], problems: list[str],
    verify_fingerprint: bool = False, warnings: Optional[list[str]] = None,
) -> Optional[PinnedSnapshot]:
    """Valida la carpeta de la instantánea y resuelve proyecto y versión.
    Agrega a `problems` todo lo que impida servirla."""
    avisos = warnings if warnings is not None else []
    directorio = Path(snapshot_dir).expanduser()
    if not directorio.is_absolute():
        avisos.append(
            f"{SNAPSHOT_DIR_VAR} es una ruta relativa ({snapshot_dir}); se resolvió contra la carpeta "
            f"desde la que se arrancó el proceso: {directorio.resolve()}. Usa una ruta absoluta."
        )
        directorio = directorio.resolve()
    if not directorio.exists():
        problems.append(f"{SNAPSHOT_DIR_VAR} apunta a una carpeta que no existe: {directorio}")
        return None
    if not directorio.is_dir():
        problems.append(f"{SNAPSHOT_DIR_VAR} debe ser una carpeta, no un archivo: {directorio}")
        return None
    project_db = directorio / "project.db"
    if not project_db.exists():
        anidada = directorio / "instantanea"
        if (anidada / "project.db").exists():
            problems.append(
                f"{SNAPSHOT_DIR_VAR} apunta a la raíz del paquete de entrega ({directorio}); debe apuntar a "
                f"su subcarpeta 'instantanea': {anidada}"
            )
        else:
            problems.append(
                f"{SNAPSHOT_DIR_VAR} no contiene project.db ({directorio}). Debe ser la carpeta "
                "'instantanea' extraída del paquete de entrega (entrega_cliente_.../instantanea)."
            )
        return None
    try:
        facts = read_project_db_facts(project_db)
    except sqlite3.DatabaseError as exc:
        problems.append(f"{project_db} no es un project.db válido: {exc}")
        return None
    if len(facts.project_ids) != 1:
        problems.append(
            f"{project_db} debería describir exactamente un proyecto y describe {len(facts.project_ids)}."
        )
        return None
    project_id = facts.project_ids[0]

    try:
        declarada = read_snapshot_identity(directorio)
        fuente = IDENTITY_FILENAME
    except SnapshotIdentityError as exc:
        problems.append(str(exc))
        return None
    if declarada is None:
        declarada = _manifest_del_paquete(directorio)
        fuente = "manifest.json del paquete de entrega"

    version_env: Optional[int] = None
    if declared_version is not None:
        try:
            version_env = int(declared_version)
            if version_env < 1:
                raise ValueError
        except ValueError:
            problems.append(f"{SNAPSHOT_VERSION_VAR} debe ser un entero >= 1 (vale {declared_version!r}).")
            return None

    if declarada is not None and declarada.project_id != project_id:
        problems.append(
            f"La instantánea es inconsistente: {fuente} declara el proyecto {declarada.project_id!r} "
            f"pero su project.db es del proyecto {project_id!r}. Vuelve a exportar el paquete de entrega."
        )
        return None

    if declarada is not None:
        version = declarada.snapshot_version
        if version_env is not None and version_env != version:
            problems.append(
                f"{SNAPSHOT_VERSION_VAR}={version_env} no coincide con la versión de la instantánea "
                f"({version}, según {fuente}). Corrige la variable o bórrala: la versión se toma de la "
                "instantánea."
            )
            return None
        origen_version = fuente
    elif version_env is not None:
        version = version_env
        origen_version = f"variable {SNAPSHOT_VERSION_VAR} (instantánea sin identidad declarada)"
        avisos.append(
            "La instantánea no trae snapshot_identity.json ni manifest.json del paquete; se confía en "
            f"{SNAPSHOT_VERSION_VAR}={version}. Vuelve a exportar el paquete con esta versión de RAG STUDIO "
            "para que la versión quede verificada."
        )
    else:
        problems.append(
            f"No se pudo determinar la versión de la instantánea en {directorio}: no trae "
            f"{IDENTITY_FILENAME} ni manifest.json del paquete. Define {SNAPSHOT_VERSION_VAR} con la versión "
            "indicada en el nombre del paquete (entrega-<proyecto>-v<N>.zip) o en su INFORME_ENTREGA.md. "
            "Ya no se asume la versión 1."
        )
        return None

    huella = declarada.content_fingerprint if declarada else None
    if verify_fingerprint and huella:
        actual = content_fingerprint(directorio)
        if actual != huella:
            problems.append(
                "El contenido de la instantánea no coincide con la huella registrada al publicarla "
                f"(registrada {huella}, actual {actual}): la carpeta fue modificada o está incompleta."
            )
            return None

    modelo = facts.embedding_model or (declarada.embedding_model if declarada else None)
    return PinnedSnapshot(
        directory=directorio, project_id=project_id, version=version, version_source=origen_version,
        embedding_model=modelo, content_fingerprint=huella,
    )


def load_runtime_config(
    env: Mapping[str, str], default_home: Optional[str] = None, verify_fingerprint: bool = False,
) -> RuntimeConfig:
    problems: list[str] = []
    warnings: list[str] = []

    # --- clave operativa -------------------------------------------------
    api_key = _limpio(env, API_KEY_VAR)
    for legacy in LEGACY_API_KEY_VARS:
        legacy_value = _limpio(env, legacy)
        if legacy_value is None:
            continue
        if api_key is None:
            api_key = legacy_value
            warnings.append(
                f"Se usó {legacy} (nombre heredado). El nombre oficial es {API_KEY_VAR}; renómbrala en tu "
                ".env/servicio."
            )
        elif legacy_value != api_key:
            problems.append(
                f"{API_KEY_VAR} y {legacy} están definidas con valores distintos. Deja solo {API_KEY_VAR}."
            )
    if api_key is None:
        problems.append(
            f"{API_KEY_VAR} no está definida: este runtime no debe exponerse sin autenticación "
            "(el .env.example del paquete de entrega trae una clave generada para esa entrega)."
        )

    # --- instantánea -----------------------------------------------------
    snapshot_dir = _limpio(env, SNAPSHOT_DIR_VAR)
    declared_version = _limpio(env, SNAPSHOT_VERSION_VAR)
    home = _limpio(env, HOME_VAR)
    pinned: Optional[PinnedSnapshot] = None
    if snapshot_dir is not None:
        pinned = resolve_pinned_snapshot(
            snapshot_dir, declared_version, problems, verify_fingerprint=verify_fingerprint, warnings=warnings,
        )
    else:
        if declared_version is not None:
            problems.append(
                f"{SNAPSHOT_VERSION_VAR} está definida pero {SNAPSHOT_DIR_VAR} no: la versión solo aplica a "
                f"una instantánea fija. Define {SNAPSHOT_DIR_VAR} con la carpeta entrega_cliente_.../instantanea."
            )
        if home is None:
            problems.append(
                f"Define {SNAPSHOT_DIR_VAR} (carpeta 'instantanea' del paquete de entrega -- modo recomendado) "
                f"o, solo para servir desde una instalación de escritorio, {HOME_VAR} de forma explícita."
            )

    installation_dir = home or default_home or ""
    if not installation_dir:
        problems.append(f"No se pudo resolver {HOME_VAR}.")

    # --- perfil de embeddings -------------------------------------------
    profile_env = _limpio(env, PROFILE_VAR)
    modelo_indice = pinned.embedding_model if pinned else None
    profile = profile_env or ""
    profile_source = f"variable {PROFILE_VAR}"
    if profile_env is not None and profile_env not in AVAILABLE_EMBEDDING_PROFILES:
        problems.append(
            f"{PROFILE_VAR}={profile_env!r} no existe. Perfiles disponibles: "
            f"{', '.join(AVAILABLE_EMBEDDING_PROFILES)}."
        )
    elif profile_env is not None and modelo_indice and EMBEDDING_MODEL_BY_PROFILE[profile_env] != modelo_indice:
        esperado = _PROFILE_BY_MODEL.get(modelo_indice)
        problems.append(
            f"{PROFILE_VAR}={profile_env!r} usa el modelo {EMBEDDING_MODEL_BY_PROFILE[profile_env]!r}, pero el "
            f"índice de la instantánea se construyó con {modelo_indice!r}"
            + (f" (perfil {esperado!r}). Usa ese perfil o bórrala." if esperado else ".")
        )
    elif profile_env is None:
        if modelo_indice and modelo_indice in _PROFILE_BY_MODEL:
            profile = _PROFILE_BY_MODEL[modelo_indice]
            profile_source = "derivado del modelo del índice de la instantánea"
        elif modelo_indice:
            problems.append(
                f"El índice de la instantánea usa el modelo {modelo_indice!r}, que no corresponde a ningún "
                f"perfil conocido ({', '.join(AVAILABLE_EMBEDDING_PROFILES)}). Define {PROFILE_VAR}."
            )
        else:
            profile = AVAILABLE_EMBEDDING_PROFILES[0]
            profile_source = "por defecto (la instantánea no registra modelo de índice)"

    # --- opcionales -------------------------------------------------------
    log_level = (_limpio(env, "RAGSTUDIO_LOG_LEVEL") or "INFO").upper()
    if log_level not in _LOG_LEVELS:
        problems.append(f"RAGSTUDIO_LOG_LEVEL={log_level!r} no es válido ({', '.join(_LOG_LEVELS)}).")
    rate_limit: Optional[int] = None
    raw_rate = _limpio(env, "RAGSTUDIO_RATE_LIMIT_PER_MINUTE")
    if raw_rate is not None:
        try:
            rate_limit = int(raw_rate)
            if rate_limit < 1:
                raise ValueError
        except ValueError:
            problems.append(f"RAGSTUDIO_RATE_LIMIT_PER_MINUTE debe ser un entero >= 1 (vale {raw_rate!r}).")
            rate_limit = None
    raw_origins = _limpio(env, "RAGSTUDIO_WIDGET_ALLOWED_ORIGINS") or ""
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()] or None
    webhook_url = _limpio(env, "RAGSTUDIO_CHANNELING_WEBHOOK_URL")
    if webhook_url is not None and not webhook_url.lower().startswith(("http://", "https://")):
        problems.append(f"RAGSTUDIO_CHANNELING_WEBHOOK_URL debe empezar con http:// o https:// ({webhook_url!r}).")

    if problems:
        raise RuntimeConfigurationError(problems)
    assert api_key is not None
    return RuntimeConfig(
        installation_dir=installation_dir, api_key=api_key, embedding_profile=profile,
        embedding_profile_source=profile_source, log_level=log_level,
        runtime_db_path=_limpio(env, "RAGSTUDIO_RUNTIME_DB_PATH"), allowed_origins=origins,
        webhook_url=webhook_url, webhook_secret=_limpio(env, "RAGSTUDIO_CHANNELING_WEBHOOK_SECRET"),
        rate_limit_per_minute=rate_limit, pinned=pinned, warnings=warnings,
    )
