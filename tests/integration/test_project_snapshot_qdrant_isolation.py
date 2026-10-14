"""Prueba de validación de la Fase 0 del plan de runtime (ADR-002,
"docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx"): confirma
de forma ejecutable, contra el paquete qdrant_client real (no un
doble), el riesgo que motiva la decisión de separar "instantáneas
publicadas" de los archivos que la app de escritorio edita en vivo, y
que esa mitigación de verdad evita el conflicto.

QdrantClient(path=...) (modo local/embebido, ver
infrastructure/vectorstores/qdrant_local_store.py) toma un lock
exclusivo sobre su directorio mientras está abierto. Sin esta
separación, un futuro runtime que leyera directamente
projects/<project_id>/indexes/qdrant competiría por ese lock con la
app de escritorio. La mitigación que adopta ADR-002 -- publicar una
copia en un directorio nuevo (snapshots/<project_id>/v<n>/...) -- se
valida aquí copiando el índice mientras el original permanece abierto
en otro cliente, y confirmando que la copia se abre de forma
independiente sin errores."""
from __future__ import annotations

import shutil

import pytest
from qdrant_client import QdrantClient

from domain.rag.entities import VectorPoint
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore


def test_opening_the_same_live_index_twice_conflicts(tmp_path):
    """Documenta el riesgo que motiva ADR-002: dos procesos no pueden
    abrir el mismo directorio de índice Qdrant embebido a la vez."""
    index_dir = tmp_path / "indexes" / "qdrant"
    index_dir.mkdir(parents=True)
    live = QdrantClient(path=str(index_dir))
    try:
        with pytest.raises(RuntimeError):
            QdrantClient(path=str(index_dir))
    finally:
        live.close()


def test_publishing_a_snapshot_copy_avoids_the_conflict(tmp_path):
    """La mitigación que adopta ADR-002 (Fase 1, PublishProjectSnapshot):
    copiar el índice a un directorio nuevo permite abrir la instantánea
    de forma independiente sin tocar ni cerrar el índice original."""
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    store = QdrantLocalVectorStore(paths)
    store.ensure_collection("p1", vector_size=4)
    store.upsert("p1", [
        VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4]),
    ])

    live_dir = paths.qdrant_index_dir("p1")
    # Simula el peor caso: algo mantiene el directorio "en vivo" abierto
    # justo en el momento de publicar (el adaptador real abre/cierra por
    # operación, pero la publicación debe ser segura incluso si coincide
    # con una operación en curso).
    live = QdrantClient(path=str(live_dir))
    try:
        snapshot_dir = paths.base_dir / "snapshots" / "p1" / "v1" / "indexes" / "qdrant"
        snapshot_dir.parent.mkdir(parents=True)
        shutil.copytree(live_dir, snapshot_dir)

        snapshot_client = QdrantClient(path=str(snapshot_dir))
        try:
            # El adaptador usa un nombre de colección fijo ("chunks") dentro
            # del directorio propio de cada proyecto -- lo relevante aquí no
            # es el nombre, sino que la copia trae los datos y se abre sola.
            collections = {c.name for c in snapshot_client.get_collections().collections}
            assert collections, "la instantánea debería conservar la colección del índice original"
            point_count = snapshot_client.count(collection_name=next(iter(collections))).count
            assert point_count == 1
        finally:
            snapshot_client.close()
    finally:
        live.close()
