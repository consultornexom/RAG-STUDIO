import pytest

from domain.ingestion.entities import Chunk, ChunkType, ExtractionRecord, FragmentationPolicy, FragmentationStrategy


def test_extraction_record_computes_char_count():
    record = ExtractionRecord(project_id="p1", source_id="s1", text="hola mundo")
    assert record.char_count == len("hola mundo")


def test_extraction_record_defaults_are_empty():
    record = ExtractionRecord(project_id="p1", source_id="s1", text="x")
    assert record.page_breaks == []
    assert record.warnings == []


def test_chunk_rejects_empty_text():
    with pytest.raises(ValueError):
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="   ", token_count=0)


def test_chunk_rejects_negative_index_or_token_count():
    with pytest.raises(ValueError):
        Chunk(project_id="p1", source_id="s1", chunk_index=-1, text="hola", token_count=1)
    with pytest.raises(ValueError):
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="hola", token_count=-1)


def test_chunk_defaults_to_texto_type_and_pipeline_version():
    chunk = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="hola", token_count=1)
    assert chunk.chunk_type.value == "texto"
    assert chunk.pipeline_version == "1.0"
    assert chunk.inherited_metadata == {}


# ---------- Pista B.1 del ADR-003: modelo canónico de Chunk ----------

def test_chunk_type_has_encabezado_and_padre_values():
    # Decisión confirmada del documento de diseño (sección 3.1):
    # reutilizar ChunkType en vez de agregar un element_type paralelo.
    assert ChunkType.ENCABEZADO.value == "encabezado"
    assert ChunkType.PADRE.value == "padre"


def test_chunk_parent_chunk_id_and_structured_content_default_to_none():
    # Ningún chunk existente antes de esta ronda tenía estos campos --
    # deben quedar en None por defecto, sin exigir que quien construya
    # un Chunk los conozca.
    chunk = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="hola", token_count=1)
    assert chunk.parent_chunk_id is None
    assert chunk.structured_content is None


def test_chunk_accepts_parent_chunk_id_and_structured_content():
    chunk = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="extracto", token_count=1,
        chunk_type=ChunkType.TEXTO, parent_chunk_id="chunk-padre-1",
        structured_content={"filas": [["a", "1"]]},
    )
    assert chunk.parent_chunk_id == "chunk-padre-1"
    assert chunk.structured_content == {"filas": [["a", "1"]]}


def test_fragmentation_policy_defaults_match_investigacion_parameters():
    policy = FragmentationPolicy(project_id="p1", document_type_code="default")
    assert policy.strategy == FragmentationStrategy.POR_TAMANIO
    assert policy.target_tokens == 500
    assert policy.overlap_tokens == 60
    assert policy.min_tokens == 80


# ---------- Pista B.2 del ADR-003: datos estructurados ----------

def test_chunk_type_has_estructurado_value():
    assert ChunkType.ESTRUCTURADO.value == "estructurado"


def test_fragmentation_strategy_has_por_hoja_estructurada_value():
    assert FragmentationStrategy.POR_HOJA_ESTRUCTURADA.value == "por_hoja_estructurada"


def test_extraction_record_structured_blocks_defaults_to_empty_dict():
    # Cualquier fuente que no sea XLSX/CSV, o una extracción hecha antes
    # de esta capacidad, debe quedar en "sin bloques" -- no None (para
    # no distinguir dos formas de "vacío" en el mismo campo).
    record = ExtractionRecord(project_id="p1", source_id="s1", text="x")
    assert record.structured_blocks == {}


def test_extraction_record_accepts_structured_blocks():
    record = ExtractionRecord(
        project_id="p1", source_id="s1", text="tabla",
        structured_blocks={"Programas": {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}},
    )
    assert record.structured_blocks["Programas"]["columnas"] == ["codigo"]


def test_fragmentation_policy_rejects_empty_document_type_code():
    with pytest.raises(ValueError):
        FragmentationPolicy(project_id="p1", document_type_code="   ")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_tokens": 0},
        {"target_tokens": -10},
        {"overlap_tokens": -1},
        {"overlap_tokens": 500},  # igual a target_tokens: inválido
        {"min_tokens": -1},
        {"min_tokens": 500},  # igual a target_tokens: inválido
    ],
)
def test_fragmentation_policy_rejects_incoherent_parameters(kwargs):
    with pytest.raises(ValueError):
        FragmentationPolicy(project_id="p1", document_type_code="default", **kwargs)


# ---------- Fase 2 de multimodalidad nativa (RAG 3): ChunkType.IMAGEN ----------

def test_chunk_type_has_imagen_value():
    assert ChunkType.IMAGEN.value == "imagen"


def test_chunk_with_type_imagen_allows_empty_text():
    # A diferencia de cualquier otro ChunkType, un chunk de imagen no
    # tiene contenido narrativo -- el contenido real vive en
    # image_relative_path, no en text.
    chunk = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="", token_count=0,
        chunk_type=ChunkType.IMAGEN, image_relative_path="sources/original/s1/foto.png",
    )
    assert chunk.text == ""
    assert chunk.image_relative_path == "sources/original/s1/foto.png"


def test_chunk_with_type_texto_still_rejects_empty_text():
    # La relajación del validador es específica de ChunkType.IMAGEN --
    # ningún otro tipo de chunk queda exento de esta regla.
    with pytest.raises(ValueError):
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="   ", token_count=0, chunk_type=ChunkType.TEXTO)


def test_chunk_image_relative_path_defaults_to_none():
    chunk = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="hola", token_count=1)
    assert chunk.image_relative_path is None
