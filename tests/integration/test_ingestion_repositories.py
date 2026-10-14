"""Pruebas de integración reales (SQLite vía Alembic) de los
repositorios del contexto Ingesta."""
import pytest

from domain.ingestion.entities import Chunk, ChunkType, ExtractionRecord, FragmentationPolicy, FragmentationStrategy
from infrastructure.database.ingestion_repositories import (
    SqlAlchemyChunkRepository, SqlAlchemyExtractionRepository, SqlAlchemyFragmentationPolicyRepository,
)
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_extraction_repository_upsert_by_source(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyExtractionRepository(paths)

    record = ExtractionRecord(project_id="p1", source_id="s1", text="primer texto", extraction_method="fake")
    repo.save(record)
    assert repo.get("p1", "s1").text == "primer texto"

    updated = ExtractionRecord(
        id=record.id, project_id="p1", source_id="s1", text="texto actualizado",
        page_breaks=[10, 20], extraction_method="fake", warnings=["ojo"],
    )
    repo.save(updated)
    fetched = repo.get("p1", "s1")
    assert fetched.text == "texto actualizado"
    assert fetched.page_breaks == [10, 20]
    assert fetched.warnings == ["ojo"]


def test_extraction_repository_round_trips_structured_blocks(tmp_path):
    # Pista B.2 del ADR-003 (migración 0015): structured_blocks debe
    # sobrevivir el viaje de ida y vuelta por get() -- no solo save().
    paths = _paths(tmp_path)
    repo = SqlAlchemyExtractionRepository(paths)
    blocks = {"Programas": {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}}

    repo.save(ExtractionRecord(project_id="p1", source_id="s1", text="tabla", structured_blocks=blocks))

    assert repo.get("p1", "s1").structured_blocks == blocks
    assert repo.list_history("p1", "s1")[0].structured_blocks == blocks


def test_extraction_repository_defaults_structured_blocks_to_empty_dict_without_them(tmp_path):
    # Sin bloques estructurados (fuente no XLSX/CSV) el campo debe leer
    # como "{}", no None -- mismo criterio que ExtractionRecord por
    # defecto (ver domain/ingestion/entities.py).
    paths = _paths(tmp_path)
    repo = SqlAlchemyExtractionRepository(paths)

    repo.save(ExtractionRecord(project_id="p1", source_id="s1", text="texto plano"))

    assert repo.get("p1", "s1").structured_blocks == {}
    assert repo.list_history("p1", "s1")[0].structured_blocks == {}


def test_extraction_repository_returns_none_for_missing_or_wrong_project(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyExtractionRepository(paths)
    repo.save(ExtractionRecord(project_id="p1", source_id="s1", text="x"))

    assert repo.get("p1", "no-existe") is None
    assert repo.get("p2", "s1") is None  # mismo project.db físico no aplica aquí, pero la firma exige project_id


# ---------- historial de extracciones (ítem 5 de la evaluación de
# madurez post-8-etapas) ----------

def test_extraction_repository_records_history_on_every_save(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyExtractionRepository(paths)

    repo.save(ExtractionRecord(project_id="p1", source_id="s1", text="versión uno", extraction_method="fake"))
    repo.save(ExtractionRecord(project_id="p1", source_id="s1", text="versión dos", extraction_method="fake"))

    history = repo.list_history("p1", "s1")
    assert [h.text for h in history] == ["versión dos", "versión uno"]  # más reciente primero
    # la extracción vigente (get) sigue siendo una sola fila
    assert repo.get("p1", "s1").text == "versión dos"


def test_extraction_repository_history_is_scoped_by_project_and_source(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyExtractionRepository(paths)
    repo.save(ExtractionRecord(project_id="p1", source_id="s1", text="de s1"))
    repo.save(ExtractionRecord(project_id="p1", source_id="s2", text="de s2"))

    history = repo.list_history("p1", "s1")
    assert len(history) == 1
    assert history[0].text == "de s1"


def test_chunk_repository_persists_and_orders_by_index(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=1, text="segundo", token_count=1),
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="primero", token_count=1),
    ]
    repo.save_many("p1", chunks)

    listed = repo.list_for_source("p1", "s1")
    assert [c.text for c in listed] == ["primero", "segundo"]


def test_chunk_repository_list_for_project_returns_chunks_from_every_source(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="fuente uno", token_count=2),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="fuente dos", token_count=2),
    ])
    repo.save_many("p2", [
        Chunk(project_id="p2", source_id="s3", chunk_index=0, text="otro proyecto", token_count=2),
    ])

    texts = {c.text for c in repo.list_for_project("p1")}
    assert texts == {"fuente uno", "fuente dos"}


def test_chunk_repository_delete_for_source_is_idempotent_refragmentation(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    repo.save_many("p1", [Chunk(project_id="p1", source_id="s1", chunk_index=0, text="v1", token_count=1)])
    assert len(repo.list_for_source("p1", "s1")) == 1

    repo.delete_for_source("p1", "s1")
    repo.save_many("p1", [Chunk(project_id="p1", source_id="s1", chunk_index=0, text="v2", token_count=1)])
    listed = repo.list_for_source("p1", "s1")
    assert len(listed) == 1
    assert listed[0].text == "v2"


def test_chunk_repository_replace_for_source_swaps_old_chunks_for_new_ones(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    repo.save_many("p1", [Chunk(project_id="p1", source_id="s1", chunk_index=0, text="v1", token_count=1)])
    repo.replace_for_source("p1", "s1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="v2", token_count=1),
    ])

    listed = repo.list_for_source("p1", "s1")
    assert len(listed) == 1
    assert listed[0].text == "v2"


def test_chunk_repository_replace_for_source_never_deletes_the_old_chunks_when_the_new_ones_fail_to_save(tmp_path):
    """Auditoría profunda (ronda posterior a la Ronda 76, ver
    bitácora): reproduce el hallazgo real contra la base de datos SQL
    de verdad (no el doble en memoria) -- si guardar los chunks nuevos
    falla dentro de la MISMA sesión que ya había puesto el DELETE en
    cola, la transacción completa debe revertirse: los chunks
    anteriores deben seguir intactos. Antes de replace_for_source(),
    delete_for_source() + save_many() por separado NUNCA notaron este
    riesgo, porque cada uno era su propia transacción ya confirmada."""
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)
    repo.save_many("p1", [Chunk(project_id="p1", source_id="s1", chunk_index=0, text="v1", token_count=1)])

    chunk_valido = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="v2", token_count=1)
    chunk_invalido = Chunk(project_id="p1", source_id="s1", chunk_index=1, text="v2b", token_count=1)
    # duplicar el mismo id fuerza un IntegrityError real de SQLite a
    # mitad del bucle de inserción, sin depender de ningún doble.
    chunk_invalido.id = chunk_valido.id

    with pytest.raises(Exception):  # noqa: B017,PT011 -- cualquier error real de SQLAlchemy/SQLite sirve aquí
        repo.replace_for_source("p1", "s1", [chunk_valido, chunk_invalido])

    listed = repo.list_for_source("p1", "s1")
    assert len(listed) == 1
    assert listed[0].text == "v1"


def test_chunk_repository_round_trips_inherited_metadata_and_pages(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    chunk = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="con metadatos", token_count=2,
        section_title="Sección A", page_start=1, page_end=2, inherited_metadata={"campus": "MERIDA"},
    )
    repo.save_many("p1", [chunk])
    fetched = repo.list_for_source("p1", "s1")[0]
    assert fetched.section_title == "Sección A"
    assert fetched.page_start == 1 and fetched.page_end == 2
    assert fetched.inherited_metadata == {"campus": "MERIDA"}


def test_chunk_repository_round_trips_parent_chunk_id_and_structured_content(tmp_path):
    # Pista B.1 del ADR-003 (migración 0014) -- parent_chunk_id y
    # structured_content son NULLABLE sin default; este round-trip
    # confirma que sobreviven el paso por SQLite/Alembic (serialización
    # JSON de structured_content, igual que inherited_metadata).
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    parent = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="sección completa", token_count=3,
        chunk_type=ChunkType.PADRE,
    )
    child = Chunk(
        project_id="p1", source_id="s1", chunk_index=1, text="extracto de la sección", token_count=3,
        parent_chunk_id=parent.id, structured_content={"filas": [["a", "1"], ["b", "2"]]},
    )
    repo.save_many("p1", [parent, child])

    fetched_parent = repo.get("p1", parent.id)
    fetched_child = repo.get("p1", child.id)
    assert fetched_parent.chunk_type == ChunkType.PADRE
    assert fetched_parent.parent_chunk_id is None
    assert fetched_child.parent_chunk_id == parent.id
    assert fetched_child.structured_content == {"filas": [["a", "1"], ["b", "2"]]}


def test_chunk_repository_leaves_parent_chunk_id_and_structured_content_as_none_by_default(tmp_path):
    # Ningún chunk existente (creado antes de esta ronda) debe verse
    # afectado -- confirma que el estado por defecto sigue siendo
    # "sin padre, sin contenido estructurado", sin backfill necesario.
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)
    repo.save_many("p1", [Chunk(project_id="p1", source_id="s1", chunk_index=0, text="normal", token_count=1)])

    fetched = repo.list_for_source("p1", "s1")[0]
    assert fetched.parent_chunk_id is None
    assert fetched.structured_content is None


def test_chunk_repository_round_trips_image_relative_path(tmp_path):
    # Migración 0020 (Ronda 68): corrige un defecto real de la Fase 2
    # (Ronda 65) -- image_relative_path se poblaba en el dominio (ver
    # IndexImageSource) pero nunca se conectó a ChunkRecord, así que
    # todo Chunk tipo IMAGEN volvía con esta ruta en None en cuanto se
    # releía de la base de datos real (aunque las pruebas contra
    # InMemoryChunkRepository nunca lo notaron, porque ese doble
    # conserva el dataclass completo).
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)

    chunk = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="", token_count=0,
        chunk_type=ChunkType.IMAGEN, image_relative_path="logo-institucional.png",
    )
    repo.save_many("p1", [chunk])

    fetched = repo.list_for_source("p1", "s1")[0]
    assert fetched.chunk_type == ChunkType.IMAGEN
    assert fetched.image_relative_path == "logo-institucional.png"


def test_chunk_repository_leaves_image_relative_path_as_none_by_default(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyChunkRepository(paths)
    repo.save_many("p1", [Chunk(project_id="p1", source_id="s1", chunk_index=0, text="normal", token_count=1)])

    fetched = repo.list_for_source("p1", "s1")[0]
    assert fetched.image_relative_path is None


def test_fragmentation_policy_repository_upsert_by_document_type(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyFragmentationPolicyRepository(paths)

    policy = FragmentationPolicy(project_id="p1", document_type_code="manual", strategy=FragmentationStrategy.POR_ENCABEZADO)
    repo.save_policy(policy)
    assert repo.get_policy("p1", "manual").strategy == FragmentationStrategy.POR_ENCABEZADO

    updated = FragmentationPolicy(
        id=policy.id, project_id="p1", document_type_code="manual",
        strategy=FragmentationStrategy.POR_TAMANIO, target_tokens=300,
    )
    repo.save_policy(updated)
    fetched = repo.get_policy("p1", "manual")
    assert fetched.strategy == FragmentationStrategy.POR_TAMANIO
    assert fetched.target_tokens == 300


def test_fragmentation_policy_repository_lists_all_for_project(tmp_path):
    paths = _paths(tmp_path)
    repo = SqlAlchemyFragmentationPolicyRepository(paths)
    repo.save_policy(FragmentationPolicy(project_id="p1", document_type_code="manual"))
    repo.save_policy(FragmentationPolicy(project_id="p1", document_type_code="faq"))
    repo.save_policy(FragmentationPolicy(project_id="p2", document_type_code="otro"))

    codes = {p.document_type_code for p in repo.list_policies("p1")}
    assert codes == {"manual", "faq"}
