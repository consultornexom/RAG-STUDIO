"""Implementación filesystem de DeploymentPackager (domain.release.ports)
-- Ronda 10 (ver Validacion_observaciones_RAG_STUDIO.md): paquete de
entrega al cliente para desplegar/operar el runtime de producción,
distinto del paquete de gobernanza de Etapa 7 (FilesystemReleasePackager).

Formato:

    entrega-<project_id>-v<version>.zip
    ├── manifest.json               (identificación del paquete + trazabilidad)
    ├── INFORME_ENTREGA.md          (informe formal, dirigido al cliente)
    ├── GUIA_DESPLIEGUE.md          (guía técnica, dirigida a quien opera el runtime)
    ├── CONTRATO_INTEGRACION.md     (Ronda 19 -- para quien construya el agente conversacional externo)
    ├── .env.example                (plantilla de variables de entorno)
    ├── widget-embed.html           (snippet listo para pegar en el sitio del cliente)
    └── instantanea/                (copia completa de la instantánea publicada)
        ├── snapshot_identity.json  (Ronda 92: proyecto, versión, modelo y huella)
        └── ... (project.db, índice Qdrant, etc. -- lo que haya en snapshot_dir)

Ronda 92: `instantanea/snapshot_identity.json` siempre viaja en el
paquete. Si la instantánea ya lo trae (publicada desde la Ronda 92) se
verifica que coincida con el proyecto y la versión del paquete; si es
anterior, se genera aquí con esos mismos datos (sin tocar la carpeta
publicada en disco). El runtime lo usa para derivar la versión al
arrancar en vez de suponer 1.
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from domain.release.entities import DeploymentPackage
from domain.release.ports import DeploymentPackager
from infrastructure.filesystem.snapshot_identity import (
    IDENTITY_FILENAME,
    build_snapshot_identity,
    read_snapshot_identity,
    write_snapshot_identity,
)


class DeploymentPackageIncompleteError(Exception):
    """La instantánea que este paquete debía incluir ya no está en
    disco (auditoría Ronda 10, hallazgos B6): a diferencia de
    `ExportDeploymentPackage.execute` (que ya valida esto antes de
    llegar aquí en el camino normal), este puerto vuelve a
    comprobarlo por su cuenta -- es el único punto que de verdad sabe
    si terminó de copiar algo, y no debe producir nunca un .zip que
    diga "incluye la instantánea" sin incluirla."""


MANIFEST_VERSION = 2


def build_identity_block(package: DeploymentPackage, identity) -> dict:
    """Ronda 95 (hallazgo de integración con NEXOM Testing Agent): qué
    identifica cada campo, sin ambigüedad.

    - project_id: proyecto de RAG STUDIO; estable entre versiones y
      exportaciones del mismo proyecto. Es la clave para agrupar versiones
      sucesivas ("AGENTE UDL" -> v2, v4...). En RAG STUDIO la unidad que se
      publica es el proyecto completo (todos sus lotes).
    - snapshot_version / snapshot_id: versión publicada; igual en todas las
      exportaciones de esa versión.
    - content_fingerprint: huella del contenido de la instantánea; dos
      exportaciones de la misma versión la comparten.
    - deployment_package_id: esta exportación física; nuevo cada vez.
    - knowledge_base_id: reservado para el contrato NEXOM Knowledge Package
      v1.0.0 (RAG-INC-01). Hoy siempre null; cuando exista será la identidad
      lógica portable, distinta de project_id (que puede cambiar si un
      proyecto se importa como copia)."""
    return {
        "project_id": package.project_id,
        "project_name": package.project_name,
        "snapshot_version": package.snapshot_version,
        "snapshot_id": package.snapshot_id,
        "content_fingerprint": identity.content_fingerprint,
        "deployment_package_id": package.id,
        "knowledge_base_id": None,
        "grouping_key": "project_id",
        "source_batches": _lotes_unicos(identity.batches),
    }


def _lotes_unicos(lotes) -> list[dict]:
    """Lotes de RAG CONTENT importados (Ronda 92), uno por huella -- una
    reimportación idéntica no aparece dos veces. Solo procedencia: no son
    unidades publicables por separado."""
    vistos: dict[str, dict] = {}
    for lote in lotes:
        huella = lote.get("huella")
        if huella and huella not in vistos:
            vistos[huella] = {"fingerprint": huella, "label": lote.get("etiqueta")}
    return list(vistos.values())


class DeploymentPackageIdentityMismatchError(Exception):
    """La instantánea declara un proyecto o una versión distintos de los
    del paquete que se está armando (Ronda 92). Nunca se empaqueta una
    identidad contradictoria."""


class FilesystemDeploymentPackager(DeploymentPackager):
    def export(self, package: DeploymentPackage, destination_path: str) -> str:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        snapshot_dir = Path(package.snapshot_dir)
        if not snapshot_dir.exists():
            raise DeploymentPackageIncompleteError(
                f"La instantánea {package.snapshot_dir!r} ya no existe en disco; "
                "no se puede armar el paquete de entrega sin ella."
            )

        # Escritura atómica (auditoría Ronda 10, hallazgo B5): se
        # escribe primero a un archivo temporal EN EL MISMO DIRECTORIO
        # del destino final (para que el renombrado sea atómico incluso
        # entre distintos sistemas de archivos montados) y solo se
        # renombra a `destination` si el zip completo se escribió sin
        # errores. Sin esto, un fallo a mitad de camino (disco lleno
        # mientras se copia una instantánea grande, permisos) dejaba un
        # .zip truncado pero con el nombre final -- indistinguible de
        # uno completo para quien lo reciba.
        identity = read_snapshot_identity(snapshot_dir)
        if identity is None:
            identity = build_snapshot_identity(snapshot_dir, package.project_id, package.snapshot_version)
            # Ronda 95 (auditoría): una instantánea anterior a la Ronda 92 se
            # identifica UNA vez y la identidad se deja junto a ella, para que
            # todas las exportaciones de esa versión compartan la misma huella
            # (antes se recalculaba en cada exportación y podía variar si el
            # índice local reescribía algún archivo interno). Si no se puede
            # escribir (carpeta de solo lectura), se sigue como antes.
            try:
                write_snapshot_identity(snapshot_dir, identity)
            except OSError:
                pass
        elif (identity.project_id, identity.snapshot_version) != (package.project_id, package.snapshot_version):
            raise DeploymentPackageIdentityMismatchError(
                f"La instantánea en {package.snapshot_dir!r} declara proyecto={identity.project_id!r} "
                f"versión={identity.snapshot_version}, pero el paquete es del proyecto "
                f"{package.project_id!r} versión {package.snapshot_version}."
            )

        temp_destination = destination.with_name(destination.name + f".{os.getpid()}.part")
        try:
            files_included = 0
            with zipfile.ZipFile(temp_destination, "w", zipfile.ZIP_DEFLATED) as zf:
                snapshot_files = [
                    p for p in sorted(snapshot_dir.rglob("*"))
                    if p.is_file() and p.relative_to(snapshot_dir).as_posix() != IDENTITY_FILENAME
                ]
                manifest = {
                    # Ronda 95: el formato del manifest se versiona; v2 agrega
                    # `deployment_package_id` y el bloque `identity`. Todas las
                    # claves de v1 se conservan con el mismo significado.
                    "manifest_version": MANIFEST_VERSION,
                    # `package_id` = id de ESTA exportación física (nuevo en
                    # cada exportación). Se conserva por compatibilidad; el
                    # nombre explícito es `deployment_package_id`.
                    "package_id": package.id,
                    "deployment_package_id": package.id,
                    "project_id": package.project_id,
                    "project_name": package.project_name,
                    "snapshot_version": package.snapshot_version,
                    "widget_token_id": package.widget_token_id,
                    "created_at": package.created_at.isoformat(),
                    # instantanea_incluida/instantanea_archivos (hallazgo
                    # B6): antes, el manifest no dejaba ningún rastro
                    # verificable de si la instantánea de verdad se
                    # incluyó, ni cuántos archivos -- un paquete sin
                    # instantánea (por la comprobación de arriba, ya no
                    # debería poder pasar, pero si algo cambiara la
                    # carpeta a mitad de la exportación) quedaba
                    # indistinguible de uno completo.
                    "instantanea_incluida": True,
                    "instantanea_archivos": len(snapshot_files) + 1,
                    # Ronda 92: identidad y huella de la instantánea, también
                    # aquí para quien inspeccione el .zip sin extraerlo.
                    "instantanea_identidad": IDENTITY_FILENAME,
                    "instantanea_huella": identity.content_fingerprint,
                    "modelo_embeddings": identity.embedding_model,
                    # Ronda 95: identidades separadas y explícitas (ver
                    # CONTRATO_INTEGRACION.md, sección "Identidades").
                    "identity": build_identity_block(package, identity),
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
                zf.writestr("INFORME_ENTREGA.md", package.informe)
                zf.writestr("GUIA_DESPLIEGUE.md", package.guia_despliegue)
                zf.writestr("CONTRATO_INTEGRACION.md", package.contrato_integracion)
                zf.writestr(".env.example", package.env_example)
                zf.writestr("widget-embed.html", package.widget_snippet)

                zf.writestr(f"instantanea/{IDENTITY_FILENAME}", identity.to_json())
                for path in snapshot_files:
                    rel = path.relative_to(snapshot_dir).as_posix()
                    zf.write(path, f"instantanea/{rel}")
                    files_included += 1

            os.replace(temp_destination, destination)
        except BaseException:
            temp_destination.unlink(missing_ok=True)
            raise

        return str(destination)
