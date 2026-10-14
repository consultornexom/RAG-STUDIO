"""Adaptador VectorStore sobre qdrant-client en modo local (sin
servidor, sin Docker). Implementa el puerto domain.rag.ports.VectorStore.

Nota de correccion respecto a ADR-001, seccion 8: el ADR nombraba
"Qdrant Edge" como adaptador por defecto. Al confirmar la API vigente
(regla de actualizacion de informacion del Documento Maestro, seccion
5) se encontro que Qdrant Edge es un producto real pero distinto: esta
en beta, orientado a dispositivos embebidos/robotica/IoT, y requiere
solicitar acceso. Lo que de verdad aplica a una app de escritorio
Windows/macOS/Linux sin servidor es el "Local Mode" estandar del
paquete qdrant-client (QdrantClient(path=...)), maduro y sin beta ni
solicitud de acceso -- confirmado con pruebas reales en este mismo
entorno de construccion (ver bitacora del README). El puerto
VectorStore permanece desacoplado precisamente para poder sustituir
esta implementacion si algo cambia.

Una coleccion fija ("chunks") por proyecto: el aislamiento entre
proyectos ya lo da el directorio (InstallationPaths.qdrant_index_dir),
igual que project.db aisla los datos relacionales -- no hace falta
ademas namespacing por project_id dentro del nombre de la coleccion.

Parametro `collection` (Fase 1 del diseno de multimodalidad nativa, ver
docs proyecto/RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx,
seccion 3.3): cada metodo acepta un nombre de coleccion explicito, con
domain.rag.entities.DEFAULT_COLLECTION_NAME ("chunks") como valor por
defecto -- ningun llamador existente pasa este parametro, asi que su
comportamiento no cambia. Desde la Fase 3 este valor por defecto (y el
parametro `collection` en si) vive en el propio puerto VectorStore, no
solo en este adaptador (ver domain.rag.ports.VectorStore) -- antes era
una constante privada de este modulo (_COLLECTION_NAME); se promovio al
dominio para que application (IndexImageSource/SemanticSearchImages)
pueda pedir la coleccion de imagenes (IMAGE_COLLECTION_NAME,
"chunks_imagenes") sin depender de este adaptador concreto. Una
coleccion con otro nombre (p. ej. "chunks_imagenes") vive dentro del
mismo QdrantClient(path=...) de ese proyecto: Qdrant admite multiples
colecciones por instancia sin conflicto, y esto evita el caso que este
mismo adaptador rechaza explicitamente en ensure_collection (vectores
con nombre dentro de UNA sola coleccion) -- aqui son dos colecciones
separadas, cada una con un solo vector sin nombre, no una coleccion con
vectores nombrados.

Ciclo de vida del cliente: QdrantClient(path=...) toma un lock
exclusivo sobre el directorio mientras esta abierto (verificado:
reabrir el mismo path despues de client.close() funciona sin
conflicto). Por eso cada metodo abre su propio cliente y lo cierra en
un try/finally, igual que _session_factory_for abre una sesion nueva
de SQLAlchemy por llamada -- evita dejar el directorio bloqueado entre
llamadas y evita compartir un cliente entre hilos del job runner.

Auditoria profunda (ronda posterior a la 76, ver bitacora): ese lock
exclusivo de qdrant-client en modo local es NO bloqueante -- si dos
hilos del MISMO proceso llaman a `_open()` sobre el mismo `project_id`
al mismo tiempo (alcanzable en la app de escritorio real: un job de
indexacion en curso sobre `project_id` mientras el usuario pulsa
"Buscar"/"Comparar modelos" en Ingesta o "Simular" en Diseño
conversacional -- ninguno de esos tres botones usa una `key` de
`ThreadJobRunner` que los serialice contra el job de indexacion, y
tampoco tendria por que: son operaciones de lectura, no deberian
bloquearse entre si por diseño), quien pierde la carrera recibe un
`RuntimeError` crudo de qdrant-client ("Storage folder ... is already
accessed by another instance") en vez de un resultado de busqueda o de
indexacion. Mismo problema, en espiritu, que el que la Ronda 10 ya
corrigio para el runtime API (`LoadedSnapshot.lock` en
interfaces/api/runtime_context.py) -- pero ese arreglo nunca llego a la
app de escritorio, porque ahi cada panel de la interfaz solo se
autolimita con su propio `_active_job`, no con un candado compartido
por proyecto. Correccion: un `threading.Lock` por `project_id`
(protegido a su vez por un lock de clase solo para crear/buscar cada
lock individual -- doble chequeo, mismo patron que
`RuntimeContext._locks` en interfaces/api/runtime_context.py) que
envuelve el cuerpo completo de cada metodo publico de este adaptador.
Esto serializa el acceso al directorio de un mismo proyecto sin
serializar proyectos distintos entre si, y sin cambiar ninguna firma
publica ni el comportamiento de ningun llamador existente.
"""
from __future__ import annotations

import threading
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from domain.rag.entities import DEFAULT_COLLECTION_NAME, VectorPoint, VectorSearchHit
from domain.rag.exceptions import EmbeddingDimensionMismatchError
from domain.rag.ports import VectorStore
from infrastructure.filesystem.paths import InstallationPaths

_COLLECTION_NAME = DEFAULT_COLLECTION_NAME
"""Alias local retenido solo para no tocar la firma de cada metodo de
abajo (valor por defecto de su parametro `collection`) -- la constante
real ahora vive en domain.rag.entities (ver docstring del modulo)."""


class QdrantLocalVectorStore(VectorStore):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, project_id: str) -> threading.Lock:
        # Doble chequeo: el candado de clase (`_locks_guard`) solo
        # protege la creacion/busqueda del candado POR PROYECTO en el
        # diccionario -- una vez obtenido, se libera de inmediato y es
        # el candado por proyecto el que de verdad serializa el acceso
        # al directorio de qdrant-client (ver docstring del modulo).
        # Proyectos distintos nunca se bloquean entre si.
        lock = self._locks.get(project_id)
        if lock is None:
            with self._locks_guard:
                lock = self._locks.setdefault(project_id, threading.Lock())
        return lock

    def _open(self, project_id: str) -> QdrantClient:
        index_dir = self._paths.qdrant_index_dir(project_id)
        index_dir.parent.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(index_dir))

    def ensure_collection(
        self, project_id: str, vector_size: int, *, collection: str = _COLLECTION_NAME,
    ) -> None:
        with self._lock_for(project_id):
            client = self._open(project_id)
            try:
                if client.collection_exists(collection):
                    info = client.get_collection(collection)
                    vectors_config = info.config.params.vectors
                    # Este adaptador siempre crea colecciones de un solo
                    # vector sin nombre (ver docstring del módulo); qdrant
                    # también admite vectores con nombre (dict) o ninguno
                    # configurado (None), pero eso nunca debería ocurrir
                    # para una colección creada por este mismo adaptador --
                    # si ocurre, es una inconsistencia real que hay que
                    # reportar, no un AttributeError críptico.
                    if not isinstance(vectors_config, VectorParams):
                        raise EmbeddingDimensionMismatchError(
                            f"El índice del proyecto {project_id!r} (colección {collection!r}) "
                            "tiene una configuración de vectores inesperada (con nombre o sin "
                            "configurar) -- no compatible con este adaptador. Borra el directorio "
                            "de índice para regenerarlo."
                        )
                    existing_size = vectors_config.size
                    if existing_size != vector_size:
                        raise EmbeddingDimensionMismatchError(
                            f"El indice del proyecto {project_id!r} (coleccion {collection!r}) "
                            f"ya existe con vectores de dimension {existing_size}, pero el "
                            f"modelo de embeddings actual produce dimension {vector_size}. Hay "
                            f"que reindexar todo el proyecto con un modelo consistente antes de "
                            f"continuar (borrar el directorio de indice o cambiar de modelo de "
                            f"vuelta)."
                        )
                    return
                client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
            finally:
                client.close()

    def upsert(
        self, project_id: str, points: list[VectorPoint], *, collection: str = _COLLECTION_NAME,
    ) -> None:
        if not points:
            return
        with self._lock_for(project_id):
            client = self._open(project_id)
            try:
                client.upsert(
                    collection_name=collection,
                    points=[
                        PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                        for p in points
                    ],
                )
            finally:
                client.close()

    def delete_for_source(
        self, project_id: str, source_id: str, *, collection: str = _COLLECTION_NAME,
    ) -> None:
        with self._lock_for(project_id):
            client = self._open(project_id)
            try:
                if not client.collection_exists(collection):
                    return
                client.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
                    ),
                )
            finally:
                client.close()

    def search(
        self, project_id: str, query_vector: list[float], limit: int,
        source_id: Optional[str] = None, *, collection: str = _COLLECTION_NAME,
    ) -> list[VectorSearchHit]:
        with self._lock_for(project_id):
            client = self._open(project_id)
            try:
                if not client.collection_exists(collection):
                    return []
                query_filter = None
                if source_id is not None:
                    query_filter = Filter(
                        must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
                    )
                results = client.query_points(
                    collection_name=collection, query=query_vector, limit=limit,
                    query_filter=query_filter,
                ).points
                return [
                    VectorSearchHit(chunk_id=str(r.id), score=r.score, payload=dict(r.payload or {}))
                    for r in results
                ]
            finally:
                client.close()

    def count(self, project_id: str, *, collection: str = _COLLECTION_NAME) -> int:
        with self._lock_for(project_id):
            client = self._open(project_id)
            try:
                if not client.collection_exists(collection):
                    return 0
                return client.count(collection_name=collection).count
            finally:
                client.close()
