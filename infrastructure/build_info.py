"""Identidad del código de RAG Studio en ejecución (Ronda 104b, Etapa 0,
autorizada por NEXOM): versión, commit y huella del código, para que cada
respuesta del Runtime y del Simulador diga con qué código se produjo.

Orden de resolución del commit:
1. `build_info.json` en la raíz del código (o junto al ejecutable
   congelado). Lo escribe `scripts/escribir_build_info.py` al preparar un
   ZIP de código o un paquete: es la vía para instalaciones sin `.git`.
2. `git rev-parse HEAD` en la raíz del código, si existe `.git` y `git`.
3. Desconocido: se informa como tal (None + lista `unknown`), nunca se
   inventa.

La huella del código (`code_fingerprint`) es independiente de git: SHA-256
de los archivos `.py` de los paquetes del producto y de las migraciones,
con rutas relativas POSIX, ordenados y con saltos de línea normalizados
(el mismo código da la misma huella en Windows, macOS y Linux). Permite
saber si un despliegue corre exactamente el código de un commit candidato
aunque no tenga `.git`: basta calcular la huella del checkout candidato
con el mismo script y comparar.

No incluye rutas, nombres de equipo ni variables de entorno.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

BUILD_INFO_FILENAME = "build_info.json"
CODE_PACKAGES = ("app", "application", "domain", "infrastructure", "interfaces", "migrations", "ui", "workers")
"""Carpetas cuyo código define el comportamiento del producto. No incluye
pruebas, documentación ni datos."""


def code_root() -> Path:
    """Raíz del código: la carpeta que contiene `infrastructure/`."""
    return Path(__file__).resolve().parents[1]


def _frozen_root() -> Optional[Path]:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


@dataclass(frozen=True)
class CodeIdentity:
    version: Optional[str]
    commit: Optional[str]
    commit_source: Optional[str]
    """"build_info", "git" o None (desconocido)."""
    dirty: Optional[bool]
    """True si el árbol tenía cambios sin commit respecto de `commit`."""
    fingerprint: Optional[str]
    fingerprint_source: Optional[str]
    """"calculada" (al arrancar), "build_info" o None (desconocida)."""
    package_fingerprints: tuple[tuple[str, str], ...] = field(default=())
    """Huella por carpeta de código presente. Permite comparar despliegues
    que no copian todas las carpetas (p. ej. la imagen Docker del Runtime no
    lleva ui/): se comparan las carpetas en común."""
    build_generated_at: Optional[str] = None
    unknown: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict:
        return {
            "version": self.version, "commit": self.commit, "commit_source": self.commit_source,
            "dirty": self.dirty, "fingerprint": self.fingerprint, "fingerprint_source": self.fingerprint_source,
            "packages": [nombre for nombre, _ in self.package_fingerprints],
            "build_generated_at": self.build_generated_at, "unknown": list(self.unknown),
        }

    def package_dict(self) -> dict[str, str]:
        return dict(self.package_fingerprints)


def _read_version(root: Path) -> Optional[str]:
    pyproject = root / "pyproject.toml"
    try:
        texto = pyproject.read_text(encoding="utf-8")
    except OSError:
        texto = ""
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', texto)
    if m:
        return m.group(1)
    try:
        from importlib.metadata import version

        return version("ragstudio")
    except Exception:  # noqa: BLE001 - sin metadatos de paquete instalado
        return None


def compute_package_fingerprints(root: Path) -> dict[str, str]:
    """Huella SHA-256 de cada carpeta de CODE_PACKAGES presente (archivos
    `.py`, rutas relativas POSIX ordenadas, saltos de línea normalizados)."""
    resultado: dict[str, str] = {}
    for paquete in CODE_PACKAGES:
        base = root / paquete
        if not base.is_dir():
            continue
        entradas = []
        for archivo in base.rglob("*.py"):
            if "__pycache__" in archivo.parts:
                continue
            contenido = archivo.read_bytes().replace(b"\r\n", b"\n")
            entradas.append((archivo.relative_to(root).as_posix(), hashlib.sha256(contenido).hexdigest()))
        if entradas:
            total = hashlib.sha256()
            for ruta, digest in sorted(entradas):
                total.update(f"{ruta}\0{digest}\n".encode())
            resultado[paquete] = total.hexdigest()
    return resultado


def combine_fingerprints(paquetes: dict[str, str]) -> Optional[str]:
    if not paquetes:
        return None
    total = hashlib.sha256()
    for nombre in sorted(paquetes):
        total.update(f"{nombre}\0{paquetes[nombre]}\n".encode())
    return total.hexdigest()


def compute_code_fingerprint(root: Path) -> Optional[str]:
    """Huella combinada de las carpetas presentes. None si no hay archivos
    `.py` (p. ej. ejecutable congelado)."""
    return combine_fingerprints(compute_package_fingerprints(root))


def _git(root: Path, *args: str) -> Optional[str]:
    if not (root / ".git").exists():
        return None
    try:
        salida = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return salida.stdout.strip()


def _read_build_info(root: Path) -> Optional[dict]:
    for base in (root, _frozen_root()):
        if base is None:
            continue
        ruta = base / BUILD_INFO_FILENAME
        if ruta.is_file():
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            return datos if isinstance(datos, dict) else None
    return None


def resolve_code_identity(root: Optional[Path] = None) -> CodeIdentity:
    root = root or code_root()
    version = _read_version(root)
    info = _read_build_info(root)
    commit = commit_source = None
    dirty: Optional[bool] = None
    generated_at = None
    if info and info.get("commit"):
        commit, commit_source = str(info["commit"]), "build_info"
        dirty = info.get("dirty") if isinstance(info.get("dirty"), bool) else None
        generated_at = info.get("generated_at")
        version = info.get("version") or version
    else:
        head = _git(root, "rev-parse", "HEAD")
        if head:
            commit, commit_source = head, "git"
            estado = _git(root, "status", "--porcelain", "--untracked-files=no")
            dirty = bool(estado) if estado is not None else None
    paquetes = compute_package_fingerprints(root)
    fingerprint = combine_fingerprints(paquetes)
    fingerprint_source = "calculada" if fingerprint else None
    if fingerprint is None and info and info.get("code_fingerprint"):
        fingerprint, fingerprint_source = str(info["code_fingerprint"]), "build_info"
        paquetes = {k: str(v) for k, v in (info.get("package_fingerprints") or {}).items()}
    desconocidos = [nombre for nombre, valor in (
        ("version", version), ("commit", commit), ("dirty", dirty), ("fingerprint", fingerprint),
    ) if valor is None]
    return CodeIdentity(
        version=version, commit=commit, commit_source=commit_source, dirty=dirty, fingerprint=fingerprint,
        fingerprint_source=fingerprint_source, package_fingerprints=tuple(sorted(paquetes.items())),
        build_generated_at=generated_at, unknown=tuple(desconocidos),
    )


@lru_cache(maxsize=1)
def current_code_identity() -> CodeIdentity:
    """Identidad del código de ESTE proceso (se calcula una vez)."""
    return resolve_code_identity()
