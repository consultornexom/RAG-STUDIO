# -*- coding: utf-8 -*-
"""Construye un RagService real (no un doble) apuntando a una copia de
trabajo de un proyecto piloto -- NUNCA al proyecto real "AGENTE UDL".
Reutiliza exactamente los mismos adaptadores que ya usa
app/bootstrap.py (RAG STUDIO real) y RuntimeContext (interfaces/api/),
vía SnapshotInstallationPaths -- la misma clase que usa el runtime HTTP
para servir una instantánea publicada sin copiar código nuevo.

Debe ejecutarse con el PYTHONPATH apuntando a la raíz del repositorio
de RAG STUDIO (para poder hacer `from application.rag.service import
RagService`, etc.) -- ver README_ejecutar_localmente.md."""
from __future__ import annotations

import json
from pathlib import Path


def build_rag_service(snapshot_dir: str | Path, runtime_scratch_dir: str | Path):
    """snapshot_dir: carpeta ya descomprimida de un .agentproj (debe
    contener project.db, indexes/qdrant/, sources/original/ en su raíz
    -- exactamente lo que produce preparar_proyecto_piloto.py).
    runtime_scratch_dir: carpeta de trabajo aparte (para la caché de
    modelos de embeddings/reranker) -- nunca escribe dentro de
    snapshot_dir, que se trata como solo-lectura (mismo criterio que
    ADR-002, sección 5, para instantáneas reales).

    Devuelve (rag_service, project_id)."""
    # Imports diferidos: solo existen si este script corre con el
    # PYTHONPATH del repositorio real de RAG STUDIO activado.
    from application.rag.service import RagService
    from infrastructure.database.document_repositories import SqlAlchemySourceRepository
    from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
    from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
    from infrastructure.embeddings.fastembed_provider import make_provider_for_profile
    from infrastructure.filesystem.paths import SnapshotInstallationPaths
    from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

    snapshot_dir = Path(snapshot_dir)
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No se encontró manifest.json en {snapshot_dir} -- ¿ya corriste "
            "preparar_proyecto_piloto.py para descomprimir el .agentproj?"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    project_id = manifest["project_id"]

    Path(runtime_scratch_dir).mkdir(parents=True, exist_ok=True)
    paths = SnapshotInstallationPaths(
        project_id=project_id, snapshot_dir=snapshot_dir, runtime_dir=runtime_scratch_dir,
    )

    chunk_repository = SqlAlchemyChunkRepository(paths)
    source_repository = SqlAlchemySourceRepository(paths)
    index_info_repository = SqlAlchemyIndexInfoRepository(paths)
    # Perfil de embeddings por defecto (el mismo que usa la app de
    # escritorio si no se elige otro) -- el proyecto piloto se indexó
    # con este perfil, así que hay que reutilizarlo para que los
    # vectores de la consulta caigan en el mismo espacio.
    embedding_provider = make_provider_for_profile(cache_dir=paths.models_dir())
    vector_store = QdrantLocalVectorStore(paths)

    rag_service = RagService(
        chunk_repository, embedding_provider, vector_store, index_info_repository,
        source_repository=source_repository,
        # Sin reranker ni image_embedding_provider a propósito: el
        # benchmark de la Fase -1 compara Sistema A (determinista) vs.
        # Sistema B (planificador) sobre EXACTAMENTE las mismas
        # capacidades -- agregar reranking solo a uno de los dos
        # contaminaría la comparación. Si más adelante se quiere medir
        # el efecto del reranker, debe activarse para ambos sistemas,
        # nunca solo para uno.
    )
    return rag_service, project_id
