"""Empaquetado portable .agentproj (ADR-001, sección 8 / RAG STUDIO.odt,
sección 12). Implementa el puerto ProjectPackager definido en domain.

Formato: un .zip con manifest.json (lista de archivos + hash sha256 de
cada uno + hash del propio manifiesto) más todo el contenido de
projects/<id>/ permitido según include_documents.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from domain.projects.entities import IdentityPolicy, Project
from domain.projects.exceptions import (
    ImportResidueError,
    IntegrityViolationError,
    ProjectDomainError,
)
from domain.projects.packaging import FileEntry, IntegrityReport, PackageManifest
from domain.projects.ports import ProjectPackager
from infrastructure.database import migrations as _migraciones
from infrastructure.database.engine import make_session_factory, make_sqlite_engine
from infrastructure.database.models import ProjectRecord
from infrastructure.database.repositories import record_to_project
from infrastructure.filesystem.paths import InstallationPaths


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_fingerprint(manifest: PackageManifest) -> str:
    payload = manifest.model_dump(mode="json", exclude={"manifest_sha256"})
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_SQLITE_WAL_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class FilesystemProjectPackager(ProjectPackager):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def _checkpoint_project_db(self, project_dir: Path) -> None:
        """Vuelca el WAL (ítem 1 de la segunda evaluación de madurez
        post-8-etapas, ver bitácora: `make_sqlite_engine` ahora abre
        SQLite en modo WAL) al archivo principal `project.db` antes de
        empaquetar, para que el paquete exportado nunca dependa de un
        `project.db-wal`/`project.db-shm` -- esos son un detalle interno
        de la conexión abierta, no parte del contenido lógico del
        proyecto. Sin este checkpoint, el .zip podría incluir cambios
        que solo viven en el WAL, y un import en otra instalación abriría
        `project.db` solo (sin su WAL) y los perdería."""
        db_path = project_dir / "project.db"
        if not db_path.exists():
            return
        engine = make_sqlite_engine(db_path)
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            engine.dispose()

    # ---------- export / backup ----------

    def export(
        self,
        project_id: str,
        destination_path: str,
        include_documents: bool = True,
    ) -> PackageManifest:
        project_dir = self._paths.project_dir(project_id)
        if not project_dir.exists():
            raise ProjectDomainError(
                f"No hay datos en disco para el proyecto {project_id!r} "
                f"({project_dir}); no se puede exportar."
            )

        self._checkpoint_project_db(project_dir)

        own_manifest_path = self._paths.manifest_path(project_id)

        files_to_include: list[tuple[Path, str]] = []
        for path in sorted(project_dir.rglob("*")):
            if path.is_dir():
                continue
            if path.name.endswith(_SQLITE_WAL_SIDECAR_SUFFIXES):
                # Sidecars transitorios del modo WAL; nunca son parte del
                # contenido lógico del proyecto (ver _checkpoint_project_db).
                continue
            if path == own_manifest_path:
                # Auditoría Ronda 48 (pruebas reales con documentos de
                # Licenciatura/): esta es la copia de referencia que la
                # propia export() escribe en disco unas líneas más abajo
                # (self._paths.manifest_path(project_id).write_text(...)),
                # no contenido del proyecto. Si se incluyera aquí, una
                # SEGUNDA exportación del mismo proyecto la encontraría
                # como un archivo más y produciría un .zip con dos
                # entradas "manifest.json" (la residual + la real que
                # escribe este mismo método más abajo), dejando el
                # paquete auto-inválido según su propio verify_integrity().
                continue
            rel = path.relative_to(project_dir).as_posix()
            if not include_documents and rel.startswith("sources/"):
                continue
            files_to_include.append((path, rel))

        project_name = self._read_project_name(project_id)

        manifest = PackageManifest(
            project_id=project_id,
            project_name=project_name,
            includes_documents=include_documents,
            files=[],
        )

        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
            for abs_path, rel_path in files_to_include:
                data = abs_path.read_bytes()
                digest = _sha256_bytes(data)
                manifest.files.append(
                    FileEntry(relative_path=rel_path, sha256=digest, size_bytes=len(data))
                )
                zf.writestr(rel_path, data)

            manifest.manifest_sha256 = _manifest_fingerprint(manifest)
            zf.writestr("manifest.json", manifest.model_dump_json(indent=2))

        # Copia de referencia en disco, junto al resto del proyecto
        # (agent_studio/projects/<id>/manifest.json, RAG STUDIO.odt sección 4).
        self._paths.manifest_path(project_id).write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        return manifest

    def backup(self, project_id: str, destination_path: str) -> PackageManifest:
        return self.export(project_id, destination_path, include_documents=True)

    # ---------- import ----------

    def inspect_package(self, package_path: str) -> PackageManifest:
        """Lee el manifest.json de un paquete ya verificado, sin escribir
        nada (Ronda 88): ImportProject lo usa para detectar colisiones de
        id y de nombre ANTES de copiar archivos."""
        with zipfile.ZipFile(package_path) as zf:
            return PackageManifest.model_validate_json(zf.read("manifest.json"))

    def has_project_data(self, project_id: str) -> bool:
        """True si projects/<id>/ existe y no está vacía."""
        project_dir = self._paths.project_dir(project_id)
        return project_dir.is_dir() and any(project_dir.iterdir())

    def quarantine_project_data(self, project_id: str) -> str:
        """Ronda 88: aparta (mueve, nunca borra) la carpeta de un proyecto
        NO registrado -- restos de una importación incompleta -- a
        <instalación>/residuos_importacion/<id>_<fecha>/. Devuelve la ruta
        nueva. Mover en vez de borrar: si algún día la carpeta resultara
        ser datos reales cuyo registro se perdió, siguen disponibles."""
        origen = self._paths.project_dir(project_id)
        destino_base = self._paths.base_dir / "residuos_importacion"
        destino_base.mkdir(parents=True, exist_ok=True)
        marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destino = destino_base / f"{project_id}_{marca}"
        shutil.move(str(origen), str(destino))
        return str(destino)

    def discard_project_data(self, project_id: str) -> None:
        """Ronda 88: borra projects/<id>/. Solo lo usa ImportProject para
        deshacer una importación que él mismo acaba de copiar y que no se
        pudo registrar -- nunca sobre un proyecto existente."""
        shutil.rmtree(self._paths.project_dir(project_id), ignore_errors=True)

    def import_project(
        self, package_path: str, new_project_id: Optional[str] = None, new_name: Optional[str] = None,
        identity_policy: IdentityPolicy = IdentityPolicy.PRESERVE,
    ) -> Project:
        """Copia el paquete a projects/<id>/ y devuelve el Project leído de
        su project.db. NO lo registra en el índice global (eso lo hace
        ImportProject con ProjectRepository.save).

        Ronda 88 (2026-10-02, hallazgo real de usuario):
        - Todo o nada: los archivos se extraen primero a una carpeta
          temporal dentro de projects/ y solo al final se renombran a
          projects/<id>/. Si algo falla, no queda ninguna carpeta a medias.
        - new_project_id ahora reescribe el project_id en TODAS las tablas
          de project.db. Antes solo cambiaba la fila de `project`: las
          fuentes, fragmentos, intenciones, reglas, casos de prueba, etc.
          conservaban el id viejo y, como los repositorios filtran por
          project_id, el proyecto importado como copia aparecía vacío.
        - new_name cambia el nombre del proyecto importado.
        """
        report = self.verify_integrity(package_path)
        if not report.is_valid:
            raise IntegrityViolationError(
                f"Paquete inválido ({package_path}): {report.error or report.mismatched_files}"
            )

        manifest = self.inspect_package(package_path)
        target_id = new_project_id or manifest.project_id
        # Auditoría Ronda 48: nunca escribir encima de datos existentes.
        # Ronda 88: ImportProject ya distingue proyecto registrado
        # (ProjectIdCollisionError) de restos sin registrar
        # (ImportResidueError) antes de llegar aquí; esto es la segunda
        # capa por si alguien llama al adaptador directamente.
        if self.has_project_data(target_id):
            raise ImportResidueError(target_id)

        projects_dir = self._paths.projects_dir()
        projects_dir.mkdir(parents=True, exist_ok=True)
        staging = projects_dir / f".importando_{target_id}_{uuid.uuid4().hex}"
        final_dir = self._paths.project_dir(target_id)
        try:
            self._extract(package_path, manifest, staging)
            staged_db = staging / "project.db"
            if not staged_db.exists():
                raise ProjectDomainError(
                    f"El paquete {package_path} no incluye project.db; no se puede "
                    f"reconstruir el registro del proyecto."
                )
            # RAG-INC-01a: la copia temporal se lleva a la versión actual del
            # esquema ANTES de hacerla visible. Así un paquete anterior a 0021
            # recibe sus identidades (y un fallo de cualquier migración, p. ej.
            # 0017 con códigos de caso repetidos) deja la instalación intacta
            # en vez de una carpeta a medio migrar en projects/<id>/.
            _migraciones.upgrade_project(staged_db)
            source_id = self._rewrite_identity(staged_db, manifest.project_id, target_id, new_name)
            if identity_policy == IdentityPolicy.FORK:
                self._fork_identities(staged_db)
            # RAG-INC-01a: el Project se lee de la copia temporal, antes de
            # hacerla visible, para que nada pueda fallar después del rename.
            project = self._leer_proyecto(staged_db, target_id, source_id)
            if final_dir.exists():
                final_dir.rmdir()  # vacía (has_project_data lo garantizó); si no, falla y se limpia
            staging.rename(final_dir)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        try:
            self._paths.ensure_project_layout(target_id)
        except BaseException:
            # Atomicidad (01a): nada a medias en projects/<id>/.
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return project

    @staticmethod
    def _leer_proyecto(db_path: Path, target_id: str, source_id: str) -> Project:
        engine = make_sqlite_engine(db_path)
        try:
            with make_session_factory(engine)() as session:
                record = session.get(ProjectRecord, target_id) or session.get(ProjectRecord, source_id)
                if record is None:
                    raise ProjectDomainError("El project.db importado no contiene un registro de proyecto.")
                return record_to_project(record)
        finally:
            engine.dispose()

    def _extract(self, package_path: str, manifest: PackageManifest, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=False)
        target_dir_resolved = target_dir.resolve()
        with zipfile.ZipFile(package_path) as zf:
            for entry in manifest.files:
                out_path = target_dir / entry.relative_path
                # Segunda capa contra Zip Slip (auditoría Ronda 46).
                if target_dir_resolved not in out_path.resolve().parents:
                    raise IntegrityViolationError(
                        f"Paquete inválido ({package_path}): la entrada "
                        f"{entry.relative_path!r} queda fuera de la carpeta "
                        f"del proyecto de destino."
                    )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(zf.read(entry.relative_path))

    @staticmethod
    def _fork_identities(db_path: Path) -> None:
        """RAG-INC-01a, política FORK (Alcance firmado, INC01-D3): el proyecto
        importado pasa a ser OTRA base de conocimiento. Sobre la copia
        temporal, en una sola transacción:
        - `knowledge_base_id` nuevo (UUID4);
        - un `lineage_id` nuevo por familia: todas las fuentes que compartían
          un linaje comparten el nuevo, así que se conserva quién supersede a
          quién;
        - ningún id local (proyecto, fuentes, chunks) cambia aquí.
        """
        con = sqlite3.connect(db_path)
        try:
            with con:
                con.execute("UPDATE project SET knowledge_base_id = ?", (str(uuid.uuid4()),))
                linajes = [r[0] for r in con.execute("SELECT DISTINCT lineage_id FROM source")]
                nuevos = {viejo: str(uuid.uuid4()) for viejo in linajes}
                con.executemany(
                    "UPDATE source SET lineage_id = ? WHERE lineage_id = ?",
                    [(nuevo, viejo) for viejo, nuevo in nuevos.items()],
                )
        finally:
            con.close()

    def read_knowledge_base_id(self, package_path: str) -> Optional[str]:
        """Lee `project.knowledge_base_id` del project.db del paquete, en una
        copia temporal FUERA de la instalación (nada se escribe en
        projects/). None si el paquete es anterior a 0021."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ragstudio_kb_") as tmp:
            destino = Path(tmp) / "project.db"
            with zipfile.ZipFile(package_path) as zf, zf.open("project.db") as origen, destino.open("wb") as d:
                shutil.copyfileobj(origen, d)
            con = sqlite3.connect(destino.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                columnas = {r[1] for r in con.execute("PRAGMA table_info(project)")}
                if "knowledge_base_id" not in columnas:
                    return None
                fila = con.execute("SELECT knowledge_base_id FROM project LIMIT 1").fetchone()
                return fila[0] if fila and fila[0] else None
            finally:
                con.close()

    @staticmethod
    def _rewrite_identity(db_path: Path, manifest_id: str, target_id: str, new_name: Optional[str]) -> str:
        """Ajusta id y nombre dentro del project.db extraído (todavía en la
        carpeta temporal). Devuelve el id que tenía el registro de
        proyecto. Se hace con sqlite3 directo y foreign_keys=OFF para
        poder cambiar a la vez la clave de `project` y todas las columnas
        project_id que la referencian."""
        con = sqlite3.connect(db_path)
        try:
            con.execute("PRAGMA foreign_keys=OFF")
            row = con.execute("SELECT id FROM project WHERE id = ?", (manifest_id,)).fetchone()
            if row is None:
                row = con.execute("SELECT id FROM project LIMIT 1").fetchone()
            if row is None:
                raise ProjectDomainError("El project.db importado no contiene un registro de proyecto.")
            source_id = row[0]
            with con:
                if source_id != target_id:
                    con.execute("UPDATE project SET id = ? WHERE id = ?", (target_id, source_id))
                    tablas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
                    for tabla in tablas:
                        columnas = {c[1] for c in con.execute(f'PRAGMA table_info("{tabla}")')}
                        if "project_id" in columnas:
                            con.execute(
                                f'UPDATE "{tabla}" SET project_id = ? WHERE project_id = ?',
                                (target_id, source_id),
                            )
                if new_name:
                    con.execute("UPDATE project SET name = ? WHERE id = ?", (new_name, target_id))
            return source_id
        finally:
            con.close()

    # ---------- integrity ----------

    def verify_integrity(self, package_path: str) -> IntegrityReport:
        package_path = str(package_path)
        try:
            with zipfile.ZipFile(package_path) as zf:
                names = set(zf.namelist())
                if "manifest.json" not in names:
                    return IntegrityReport(
                        package_path=package_path, is_valid=False, checked_files=0,
                        error="El paquete no contiene manifest.json",
                    )
                manifest = PackageManifest.model_validate_json(zf.read("manifest.json"))

                expected_fingerprint = manifest.manifest_sha256
                actual_fingerprint = _manifest_fingerprint(manifest)
                if expected_fingerprint != actual_fingerprint:
                    return IntegrityReport(
                        package_path=package_path, is_valid=False,
                        checked_files=len(manifest.files),
                        error="El hash del manifiesto no coincide (manifiesto alterado).",
                    )

                missing: list[str] = []
                mismatched: list[str] = []
                for entry in manifest.files:
                    if entry.relative_path not in names:
                        missing.append(entry.relative_path)
                        continue
                    data = zf.read(entry.relative_path)
                    if _sha256_bytes(data) != entry.sha256:
                        mismatched.append(entry.relative_path)

                is_valid = not missing and not mismatched
                return IntegrityReport(
                    package_path=package_path, is_valid=is_valid,
                    checked_files=len(manifest.files),
                    mismatched_files=mismatched, missing_files=missing,
                )
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError) as exc:
            return IntegrityReport(
                package_path=package_path, is_valid=False, checked_files=0, error=str(exc)
            )
        except ValidationError as exc:
            # Auditoría Ronda 46, hallazgo crítico -- Zip Slip: un
            # manifiesto con una entrada relative_path insegura
            # ("../...", ruta absoluta) falla la validación de
            # dominio (domain/projects/packaging.py::FileEntry) al
            # parsear el JSON. Antes de este hallazgo, esa situación
            # no llegaba a pasar por aquí porque nada la validaba --
            # se trata igual que un manifiesto corrupto: paquete
            # inválido, nunca una excepción sin manejar.
            return IntegrityReport(
                package_path=package_path, is_valid=False, checked_files=0,
                error=f"El manifiesto contiene datos inválidos (posible ruta insegura): {exc}",
            )

    # ---------- helpers ----------

    def _read_project_name(self, project_id: str) -> str:
        db_path = self._paths.project_db_path(project_id)
        if not db_path.exists():
            return project_id
        session_factory = make_session_factory(make_sqlite_engine(db_path))
        with session_factory() as session:
            record = session.get(ProjectRecord, project_id)
            return record.name if record else project_id
