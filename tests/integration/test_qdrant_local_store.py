"""Prueba de integracion real de QdrantLocalVectorStore -- contra el
paquete qdrant_client de verdad (modo local, sin servidor, sin red),
no un doble. Formaliza la verificacion manual hecha al construir el
adaptador (ver bitacora del README)."""
from __future__ import annotations

import threading

from domain.rag.entities import IMAGE_COLLECTION_NAME, VectorPoint
from domain.rag.exceptions import EmbeddingDimensionMismatchError
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore


def _make_store(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return QdrantLocalVectorStore(paths)


def test_ensure_collection_creates_it_once(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    assert store.count("p1") == 0
    # Llamar dos veces con la misma dimensión no debe fallar.
    store.ensure_collection("p1", vector_size=4)


def test_ensure_collection_rejects_dimension_change(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    try:
        store.ensure_collection("p1", vector_size=8)
        raise AssertionError("debía lanzar EmbeddingDimensionMismatchError")
    except EmbeddingDimensionMismatchError:
        pass


def test_upsert_and_search_real_qdrant(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.upsert("p1", [
        VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4],
                    payload={"source_id": "s1"}),
        VectorPoint(id="22222222-2222-2222-2222-222222222222", vector=[0.9, 0.8, 0.7, 0.6],
                    payload={"source_id": "s2"}),
    ])
    assert store.count("p1") == 2

    hits = store.search("p1", [0.1, 0.2, 0.3, 0.4], limit=5)
    assert hits[0].chunk_id == "11111111-1111-1111-1111-111111111111"
    assert hits[0].score > hits[1].score


def test_search_can_filter_by_source_id(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.upsert("p1", [
        VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4],
                    payload={"source_id": "s1"}),
        VectorPoint(id="22222222-2222-2222-2222-222222222222", vector=[0.9, 0.8, 0.7, 0.6],
                    payload={"source_id": "s2"}),
    ])
    hits = store.search("p1", [0.1, 0.2, 0.3, 0.4], limit=5, source_id="s2")
    assert len(hits) == 1
    assert hits[0].chunk_id == "22222222-2222-2222-2222-222222222222"


def test_delete_for_source_removes_only_its_points(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.upsert("p1", [
        VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4],
                    payload={"source_id": "s1"}),
        VectorPoint(id="22222222-2222-2222-2222-222222222222", vector=[0.9, 0.8, 0.7, 0.6],
                    payload={"source_id": "s2"}),
    ])
    store.delete_for_source("p1", "s1")
    assert store.count("p1") == 1
    hits = store.search("p1", [0.9, 0.8, 0.7, 0.6], limit=5)
    assert hits[0].chunk_id == "22222222-2222-2222-2222-222222222222"


def test_operations_on_project_without_collection_are_safe(tmp_path):
    """Antes de indexar nada, count/search/delete no deben fallar ni
    crear una colección vacía por accidente."""
    store = _make_store(tmp_path)
    assert store.count("p1") == 0
    assert store.search("p1", [0.1, 0.2, 0.3, 0.4], limit=5) == []
    store.delete_for_source("p1", "s1")  # no debe lanzar


def test_two_projects_are_fully_isolated(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.ensure_collection("p2", vector_size=8)  # dimensión distinta: si compartieran índice, esto fallaría
    store.upsert("p1", [VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4])])
    assert store.count("p1") == 1
    assert store.count("p2") == 0


def test_reopening_after_operations_does_not_lock(tmp_path):
    """Cada método abre y cierra su propio QdrantClient (ver docstring
    del adaptador) -- confirma que llamadas sucesivas no dejan el
    directorio bloqueado."""
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.upsert("p1", [VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4])])
    assert store.count("p1") == 1
    assert store.count("p1") == 1  # una segunda llamada independiente, mismo resultado


# ---------- parametro `collection` (Fase 1, multimodalidad nativa --
# ver docs proyecto/RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx,
# seccion 3.3) ----------

def test_default_collection_behavior_is_unchanged_without_the_new_parameter(tmp_path):
    """Ningun llamador existente pasa `collection` -- confirma que el
    valor por defecto sigue siendo exactamente "chunks", mismo
    comportamiento que antes de esta ronda."""
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.upsert("p1", [VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4])])
    assert store.count("p1") == 1
    assert store.count("p1", collection="chunks") == 1


def test_second_named_collection_is_isolated_from_the_default_one(tmp_path):
    """Una coleccion con otro nombre (p. ej. "chunks_imagenes") vive
    aislada de "chunks" dentro del mismo directorio de proyecto -- ni
    upsert ni delete ni count de una afectan a la otra."""
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.ensure_collection("p1", vector_size=3, collection="chunks_imagenes")

    store.upsert("p1", [VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4])])
    store.upsert(
        "p1",
        [VectorPoint(id="22222222-2222-2222-2222-222222222222", vector=[0.9, 0.8, 0.7])],
        collection="chunks_imagenes",
    )

    assert store.count("p1") == 1
    assert store.count("p1", collection="chunks_imagenes") == 1


def test_second_collection_can_use_a_different_vector_dimension(tmp_path):
    """Dimensiones distintas por coleccion (texto vs. imagen) no deben
    disparar EmbeddingDimensionMismatchError -- son indices separados,
    no una sola coleccion con vectores nombrados."""
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=384)  # texto, dimension real del default
    store.ensure_collection("p1", vector_size=512, collection="chunks_imagenes")  # imagen, CLIP


def test_search_and_delete_respect_the_collection_parameter(tmp_path):
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4, collection="chunks_imagenes")
    store.upsert(
        "p1",
        [
            VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1, 0.2, 0.3, 0.4],
                        payload={"source_id": "s1"}),
        ],
        collection="chunks_imagenes",
    )

    # No debe aparecer en la colección por defecto (que ni siquiera existe todavía).
    assert store.search("p1", [0.1, 0.2, 0.3, 0.4], limit=5) == []
    assert store.count("p1") == 0

    hits = store.search("p1", [0.1, 0.2, 0.3, 0.4], limit=5, collection="chunks_imagenes")
    assert len(hits) == 1
    assert hits[0].chunk_id == "11111111-1111-1111-1111-111111111111"

    store.delete_for_source("p1", "s1", collection="chunks_imagenes")
    assert store.count("p1", collection="chunks_imagenes") == 0


# ---------- promoción a domain.rag.entities (Fase 3) ----------

# ---------- concurrencia real dentro del mismo proceso (auditoria
# profunda posterior a la Ronda 76, ver bitacora) ----------

def test_concurrent_upsert_and_search_on_the_same_project_do_not_crash(tmp_path):
    """Reproduce el escenario real de la app de escritorio: un hilo de
    fondo indexando (upsert) sobre `project_id` mientras otro hilo (p.
    ej. "Buscar"/"Comparar modelos"/"Simular", ninguno de los tres
    serializado por una `key` de ThreadJobRunner porque son lecturas)
    abre el MISMO directorio de qdrant-client al mismo tiempo. El lock
    de archivo que usa qdrant-client en modo local es exclusivo y NO
    BLOQUEANTE -- sin el candado por proyecto de este adaptador
    (_lock_for), el segundo hilo en llegar recibe un RuntimeError crudo
    ("Storage folder ... is already accessed by another instance") en
    vez de esperar su turno. Esta prueba falla de forma intermitente
    pero real sin el candado, y pasa siempre con él."""
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)

    errors: list[Exception] = []
    iterations = 25

    def upsert_repeatedly() -> None:
        for i in range(iterations):
            try:
                store.upsert("p1", [
                    VectorPoint(
                        id=f"{i:08x}-1111-1111-1111-111111111111",
                        vector=[0.1, 0.2, 0.3, 0.4], payload={"source_id": "s1"},
                    ),
                ])
            except Exception as exc:  # noqa: BLE001 -- se captura para poder afirmar la lista vacía
                errors.append(exc)

    def search_repeatedly() -> None:
        for _ in range(iterations):
            try:
                store.search("p1", [0.1, 0.2, 0.3, 0.4], limit=5)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=upsert_repeatedly), threading.Thread(target=search_repeatedly)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


def test_concurrent_access_to_different_projects_is_not_serialized_against_each_other(tmp_path):
    """El candado es POR PROYECTO -- confirma que dos proyectos
    distintos no se bloquean entre si (cada uno tiene su propio
    threading.Lock en QdrantLocalVectorStore._locks)."""
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=4)
    store.ensure_collection("p2", vector_size=4)

    lock_p1 = store._lock_for("p1")
    lock_p2 = store._lock_for("p2")
    assert lock_p1 is not lock_p2

    # Si p1 esta "ocupado", p2 debe poder tomarse de inmediato.
    acquired_p2_promptly = []

    def hold_p1_lock() -> None:
        with lock_p1:
            acquired_p2_promptly.append(lock_p2.acquire(timeout=2))
            lock_p2.release()

    t = threading.Thread(target=hold_p1_lock)
    t.start()
    t.join()

    assert acquired_p2_promptly == [True]


def test_image_collection_name_constant_works_as_the_collection_parameter(tmp_path):
    """domain.rag.entities.IMAGE_COLLECTION_NAME (Fase 3) debe ser
    exactamente el nombre "chunks_imagenes" ya probado arriba -- esta
    prueba fija que ambos son intercambiables, no solo iguales por
    coincidencia de texto."""
    assert IMAGE_COLLECTION_NAME == "chunks_imagenes"
    store = _make_store(tmp_path)
    store.ensure_collection("p1", vector_size=512, collection=IMAGE_COLLECTION_NAME)
    store.upsert(
        "p1",
        [VectorPoint(id="11111111-1111-1111-1111-111111111111", vector=[0.1] * 512)],
        collection=IMAGE_COLLECTION_NAME,
    )
    assert store.count("p1", collection=IMAGE_COLLECTION_NAME) == 1
    assert store.count("p1") == 0  # la colección de texto sigue sin existir
