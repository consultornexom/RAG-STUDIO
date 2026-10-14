"""Identidad autodescriptiva de una instantánea publicada (Ronda 92,
2026-10-06, hallazgo real de usuario al desplegar un paquete de entrega).

Problema: la carpeta `instantanea/` de un paquete de entrega no decía qué
versión era. El runtime tomaba la versión de `RAGSTUDIO_SNAPSHOT_VERSION`
y, si no estaba definida, asumía 1 en silencio. Con una instantánea v2
eso producía una identidad falsa (proyecto:1) que los consumidores
posteriores (NEXOM Testing Agent / Agent Runtime) rechazaban con un error
de identidad de recuperación, sin pista de la causa.

Ahora cada instantánea lleva `snapshot_identity.json` dentro de su propia
carpeta. Lo escribe la publicación (FilesystemProjectSnapshotPublisher) y,
para instantáneas publicadas antes de esta ronda, el empaquetador de
entrega lo agrega al .zip a partir de los datos que ya conoce. El runtime
lo lee al arrancar para derivar la versión y validar la configuración.

Reglas de portabilidad (SOLICITUD NEXOM, documento 08):
- Sin rutas absolutas, nombre de equipo ni de usuario.
- La huella de contenido (`content_fingerprint`) usa rutas relativas con
  separador "/" y archivos ordenados: el mismo contenido da la misma
  huella en cualquier equipo. No incluye este mismo archivo.
- `published_at` es solo informativo: no participa en la huella.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

IDENTITY_FILENAME = "snapshot_identity.json"
IDENTITY_FORMAT = "ragstudio.snapshot_identity"
IDENTITY_FORMAT_VERSION = 1

_ARCHIVOS_EXCLUIDOS_DE_HUELLA = frozenset({IDENTITY_FILENAME})
_SUFIJOS_VOLATILES = ("-wal", "-shm", "-journal", ".lock")
"""Archivos que SQLite/Qdrant crean o modifican al abrir la instantánea:
no son contenido lógico y cambiarían la huella sin cambio real."""


class SnapshotIdentityError(ValueError):
    """`snapshot_identity.json` existe pero no se puede leer o es inválido."""


@dataclass(frozen=True)
class SnapshotIdentity:
    project_id: str
    snapshot_version: int
    published_at: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None
    content_fingerprint: Optional[str] = None
    fingerprint_fields: tuple[str, ...] = ("ruta_relativa_posix", "sha256_del_archivo")
    batches: tuple[dict, ...] = ()
    """Ronda 92 (multi-lote): lotes de RAG CONTENT que alimentaron el
    proyecto -- huella, etiqueta, relación y fuentes registradas -- para
    que Testing Agent/Runtime conserven la procedencia por lote."""

    def to_json(self) -> str:
        data = {
            "format": IDENTITY_FORMAT,
            "format_version": IDENTITY_FORMAT_VERSION,
            "project_id": self.project_id,
            "snapshot_version": self.snapshot_version,
            "published_at": self.published_at,
            "embedding": {
                "provider": self.embedding_provider,
                "model": self.embedding_model,
                "dimensions": self.embedding_dimensions,
            },
            "content_fingerprint": self.content_fingerprint,
            "fingerprint_fields": list(self.fingerprint_fields),
            "lotes": [dict(lote) for lote in self.batches],
        }
        return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _es_volatil(rel: str) -> bool:
    return rel in _ARCHIVOS_EXCLUIDOS_DE_HUELLA or rel.endswith(_SUFIJOS_VOLATILES)


def content_fingerprint(snapshot_dir: str | Path) -> str:
    """sha256 sobre (ruta relativa con "/", sha256 del archivo) de cada
    archivo, en orden. Independiente de la ruta física y del equipo."""
    base = Path(snapshot_dir)
    total = hashlib.sha256()
    for path in sorted((p for p in base.rglob("*") if p.is_file()), key=lambda p: p.relative_to(base).as_posix()):
        rel = path.relative_to(base).as_posix()
        if _es_volatil(rel):
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for bloque in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(bloque)
        total.update(rel.encode("utf-8") + b"\0" + digest.hexdigest().encode("ascii") + b"\n")
    return "sha256:" + total.hexdigest()


@dataclass(frozen=True)
class ProjectDbFacts:
    """Lo que el propio project.db de la instantánea dice de sí mismo."""

    project_ids: tuple[str, ...]
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None


def read_project_db_facts(project_db: str | Path) -> ProjectDbFacts:
    """Lee (en modo solo lectura, sin migrar ni crear nada) el id del
    proyecto y el modelo de embeddings con que se construyó el índice.
    Lanza sqlite3.DatabaseError si el archivo no es una base válida."""
    uri = Path(project_db).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tablas = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "project" not in tablas:
            raise sqlite3.DatabaseError("no contiene la tabla 'project' (no es un project.db de RAG STUDIO)")
        ids = tuple(row[0] for row in connection.execute("SELECT id FROM project ORDER BY id"))
        provider = model = None
        dimensions: Optional[int] = None
        if "index_info" in tablas:
            row = connection.execute(
                "SELECT embedding_provider, embedding_model, dimensions FROM index_info LIMIT 1"
            ).fetchone()
            if row:
                provider, model, dimensions = row[0], row[1], row[2]
        return ProjectDbFacts(ids, provider, model, dimensions)
    finally:
        connection.close()


def build_snapshot_identity(
    snapshot_dir: str | Path, project_id: str, snapshot_version: int,
    published_at: Optional[datetime] = None,
) -> SnapshotIdentity:
    """`published_at=None` deja la fecha como desconocida (instantáneas
    anteriores a la Ronda 92 que se identifican al empaquetarlas)."""
    base = Path(snapshot_dir)
    facts: Optional[ProjectDbFacts] = None
    if (base / "project.db").exists():
        try:
            facts = read_project_db_facts(base / "project.db")
        except sqlite3.DatabaseError:
            facts = None
    return SnapshotIdentity(
        project_id=project_id, snapshot_version=int(snapshot_version),
        published_at=(
            published_at.astimezone(timezone.utc).isoformat(timespec="seconds") if published_at else None
        ),
        embedding_provider=facts.embedding_provider if facts else None,
        embedding_model=facts.embedding_model if facts else None,
        embedding_dimensions=facts.embedding_dimensions if facts else None,
        content_fingerprint=content_fingerprint(base),
        batches=_resumen_lotes(base),
    )


def _resumen_lotes(base: Path) -> tuple[dict, ...]:
    from .import_batch_ledger import LEDGER_FILENAME, read_ledger_file

    resumen = []
    for lote in read_ledger_file(base / LEDGER_FILENAME):
        resumen.append({
            "huella": lote.fingerprint,
            "etiqueta": lote.label,
            "relacion": lote.relation,
            "lote_relacionado": lote.related_label,
            "importado_en": lote.imported_at,
            "completo": lote.complete,
            "fuentes": sorted({fila.source_id for fila in lote.rows if fila.source_id}),
        })
    return tuple(resumen)


def write_snapshot_identity(snapshot_dir: str | Path, identity: SnapshotIdentity) -> Path:
    destino = Path(snapshot_dir) / IDENTITY_FILENAME
    destino.write_bytes(identity.to_json().encode("utf-8"))
    return destino


def parse_snapshot_identity(raw: bytes | str, origen: str = IDENTITY_FILENAME) -> SnapshotIdentity:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SnapshotIdentityError(f"{origen} no es JSON válido: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != IDENTITY_FORMAT:
        raise SnapshotIdentityError(f"{origen} no tiene el formato {IDENTITY_FORMAT!r}.")
    if data.get("format_version") != IDENTITY_FORMAT_VERSION:
        raise SnapshotIdentityError(
            f"{origen} usa format_version={data.get('format_version')!r}; esta versión de RAG STUDIO "
            f"entiende {IDENTITY_FORMAT_VERSION}. Actualiza el runtime o vuelve a exportar el paquete."
        )
    project_id = data.get("project_id")
    version = data.get("snapshot_version")
    if not isinstance(project_id, str) or not project_id:
        raise SnapshotIdentityError(f"{origen}: falta 'project_id'.")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SnapshotIdentityError(f"{origen}: 'snapshot_version' debe ser un entero >= 1 (vale {version!r}).")
    embedding = data.get("embedding") or {}
    return SnapshotIdentity(
        project_id=project_id, snapshot_version=version, published_at=data.get("published_at"),
        embedding_provider=embedding.get("provider"), embedding_model=embedding.get("model"),
        embedding_dimensions=embedding.get("dimensions"),
        content_fingerprint=data.get("content_fingerprint"),
        fingerprint_fields=tuple(data.get("fingerprint_fields") or ()),
        batches=tuple(data.get("lotes") or ()),
    )


def read_snapshot_identity(snapshot_dir: str | Path) -> Optional[SnapshotIdentity]:
    """La identidad declarada dentro de la instantánea, o None si la
    instantánea es anterior a la Ronda 92 y no la trae."""
    archivo = Path(snapshot_dir) / IDENTITY_FILENAME
    if not archivo.exists():
        return None
    return parse_snapshot_identity(archivo.read_bytes(), str(archivo.name))
