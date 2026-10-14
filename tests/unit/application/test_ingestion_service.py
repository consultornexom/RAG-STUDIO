import pytest

from application.documents.service import DocumentService
from application.ingestion.service import IngestionService
from application.metadata.service import MetadataService
from domain.documents.entities import SourceType
from domain.documents.exceptions import SourceNotFoundError
from domain.ingestion.entities import ChunkType, FragmentationStrategy
from domain.ingestion.exceptions import (
    EmptyExtractionError,
    ExtractionNotFoundError,
    SourceLocationUnreadableError,
    UnsupportedSourceTypeError,
)

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import (
    FailingTokenCounter, FakeTextExtractor, FakeTokenCounter, InMemoryChunkRepository,
    InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository,
)
from .fakes_metadata import InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository


def _build_services(token_counter=None):
    source_repository = InMemorySourceRepository()
    # Una sola instancia de InMemoryExtractionRepository, compartida
    # entre document_service e ingestion_service: DocumentService la
    # necesita para saber si ya hay una extracción guardada antes de
    # permitir editar location/source_type (ver
    # UpdateSourceDetails/SourceStructuralFieldsLockedError) -- si cada
    # servicio tuviera su propia instancia en memoria, esa consulta
    # nunca vería lo que el otro servicio ya guardó.
    extraction_repository = InMemoryExtractionRepository()
    document_service = DocumentService(source_repository, extraction_repository)

    schema_repository = InMemoryMetadataSchemaRepository()
    catalog_repository = InMemoryCatalogRepository()
    source_metadata_repository = InMemorySourceMetadataRepository()
    metadata_service = MetadataService(schema_repository, catalog_repository, source_metadata_repository, source_repository)

    extractor = FakeTextExtractor()
    ingestion_service = IngestionService(
        source_repository, extractor, extraction_repository, InMemoryFragmentationPolicyRepository(),
        InMemoryChunkRepository(), schema_repository, source_metadata_repository, token_counter=token_counter,
    )
    return document_service, metadata_service, ingestion_service


@pytest.fixture
def services():
    return _build_services()


def test_extract_source_text_success(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")

    record = ingestion_service.extract_source_text("p1", source.id)
    assert record.source_id == source.id
    assert "contenido de prueba" in record.text
    assert record.char_count == len(record.text)


def test_extract_source_text_records_history_including_first_extraction(services):
    # A diferencia del historial de metadatos, aquí cada corrida se
    # registra siempre -- incluida la primera -- porque cada
    # extracción es un evento real por sí mismo (ítem 5 de la
    # evaluación de madurez post-8-etapas).
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")

    ingestion_service.extract_source_text("p1", source.id)

    history = ingestion_service.list_extraction_history("p1", source.id)
    assert len(history) == 1
    assert "contenido de prueba" in history[0].text


def test_re_extraction_appends_to_history_without_losing_the_previous_attempt(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    extractor = ingestion_service._extract._extractor
    extractor._canned["/x.txt"] = ("versión uno", "fake", [], [])

    ingestion_service.extract_source_text("p1", source.id)
    extractor._canned["/x.txt"] = ("versión dos", "fake", [], [])
    ingestion_service.extract_source_text("p1", source.id)

    history = ingestion_service.list_extraction_history("p1", source.id)
    assert len(history) == 2
    assert history[0].text == "versión dos"  # más reciente primero
    assert history[1].text == "versión uno"
    # la extracción vigente (get_extraction_record) sigue siendo una
    # sola fila -- el historial no cambia ese comportamiento.
    current = ingestion_service.get_extraction_record("p1", source.id)
    assert current.text == "versión dos"


def test_extraction_history_is_empty_before_any_extraction(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    assert ingestion_service.list_extraction_history("p1", source.id) == []


def test_extract_source_text_missing_source_raises(services):
    _, _, ingestion_service = services
    with pytest.raises(SourceNotFoundError):
        ingestion_service.extract_source_text("p1", "no-existe")


def test_extract_source_text_unsupported_type_raises(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Hoja", SourceType.XLSX, location="/x.xlsx")
    with pytest.raises(UnsupportedSourceTypeError):
        ingestion_service.extract_source_text("p1", source.id)


def test_extract_source_text_empty_result_raises(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Vacío", SourceType.TXT, location="/vacio.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/vacio.txt": ("   ", "fake", [], [])})
    with pytest.raises(EmptyExtractionError):
        ingestion_service.extract_source_text("p1", source.id)


def test_extract_source_text_imagen_nativa_allows_empty_text_without_raising(services):
    # Fase 2 de multimodalidad nativa (RAG 3): a diferencia de cualquier
    # otro tipo de fuente, texto vacío es el resultado correcto y
    # esperado para SourceType.IMAGEN_NATIVA -- no debe convertirse en
    # EmptyExtractionError (ver ImageNativeExtractor).
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Foto", SourceType.IMAGEN_NATIVA, location="/foto.png")
    ingestion_service._extract._extractor = FakeTextExtractor(
        canned={"/foto.png": ("", "imagen_nativa", [], [])},
        supported_types={SourceType.IMAGEN_NATIVA},
    )

    record = ingestion_service.extract_source_text("p1", source.id)

    assert record.text == ""
    assert record.extraction_method == "imagen_nativa"


def test_extract_source_text_normalizes_whitespace_when_no_page_breaks(services):
    # Normalización (RAG STUDIO.odt): se aplica cuando la extracción no
    # trae saltos de página (TXT/DOCX/XLSX/CSV/imagen) -- ver
    # domain/ingestion/normalization.py.
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Con espacios", SourceType.TXT, location="/messy.txt")
    messy = "Titulo   \r\n\r\n\r\n\r\nParrafo.  \n\n\nFinal.  "
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/messy.txt": (messy, "fake", [], [])})

    record = ingestion_service.extract_source_text("p1", source.id)
    assert record.text == "Titulo\n\nParrafo.\n\nFinal."


def test_extract_source_text_does_not_normalize_when_page_breaks_present(services):
    # PDF sí trae saltos de página: no se normaliza el texto completo
    # después, para no invalidar los desplazamientos ya calculados
    # (trazabilidad de página, A2).
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Con páginas", SourceType.TXT, location="/paginado.txt")
    messy = "Pagina uno.   \n\n\n\nPagina dos.  "
    ingestion_service._extract._extractor = FakeTextExtractor(
        canned={"/paginado.txt": (messy, "fake", [20], [])}
    )

    record = ingestion_service.extract_source_text("p1", source.id)
    assert record.text == messy


def test_extract_source_text_persists_structured_blocks_from_extractor(services):
    # Pista B.2 del ADR-003: lo que devuelve
    # extractor.extract_structured_blocks() debe llegar intacto al
    # ExtractionRecord guardado -- no solo el texto de extract().
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Catálogo", SourceType.XLSX, location="/catalogo.xlsx")
    ingestion_service._extract._extractor = FakeTextExtractor(
        supported_types={SourceType.XLSX},
        canned={"/catalogo.xlsx": ("## Programas\n\n| codigo |\n| --- |\n| ISC |", "xlsx", [], [])},
        canned_structured={"/catalogo.xlsx": {"Programas": {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}}},
    )

    record = ingestion_service.extract_source_text("p1", source.id)
    assert record.structured_blocks == {"Programas": {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}}


def test_extract_source_text_structured_blocks_default_to_empty_dict(services):
    # Una fuente TXT (sin capacidad de bloques estructurados) no debe
    # fallar ni requerir configuración especial -- FakeTextExtractor sin
    # canned_structured ya devuelve {} por defecto, igual que el puerto
    # real (domain.ingestion.ports.TextExtractor.extract_structured_blocks).
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")

    record = ingestion_service.extract_source_text("p1", source.id)
    assert record.structured_blocks == {}


def test_extract_source_text_wraps_os_error_in_clear_domain_error(services):
    """Hallazgo real de validación visual: registrar una fuente con la
    carpeta contenedora en 'Ubicación' (en vez de la ruta completa del
    archivo) hacía que la extracción lanzara un IsADirectoryError crudo
    ("[Errno 21] Es un directorio: '...'") hasta la UI. Ahora se
    envuelve en un error de dominio con instrucciones claras."""
    document_service, _, ingestion_service = services
    source = document_service.register_source(
        "p1", "Ficha", SourceType.TXT, location="/alguna/carpeta",
    )
    ingestion_service._extract._extractor = FakeTextExtractor(
        raise_os_error=IsADirectoryError(21, "Es un directorio")
    )
    with pytest.raises(SourceLocationUnreadableError):
        ingestion_service.extract_source_text("p1", source.id)


def test_fragment_source_without_extraction_raises(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    with pytest.raises(ExtractionNotFoundError):
        ingestion_service.fragment_source("p1", source.id)


def test_fragment_source_por_tamanio_produces_linked_chunks(services):
    document_service, _, ingestion_service = services
    text = " ".join(f"palabra{i}" for i in range(60))
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/big.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/big.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy(
        "p1", "default", strategy=FragmentationStrategy.POR_TAMANIO, target_tokens=20, overlap_tokens=5, min_tokens=5,
    )
    chunks = ingestion_service.fragment_source("p1", source.id)
    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.previous_chunk_id == (chunks[i - 1].id if i > 0 else None)
        assert chunk.next_chunk_id == (chunks[i + 1].id if i < len(chunks) - 1 else None)
        assert chunk.token_count > 0


def test_fragment_source_keeps_the_old_chunks_when_saving_the_new_ones_fails(services):
    # Auditoría profunda (ronda posterior a la 76, ver bitácora):
    # antes de replace_for_source() (ver domain.ingestion.ports.
    # ChunkRepository), FragmentSource.execute() llamaba a
    # delete_for_source() y save_many() por separado -- si el segundo
    # paso fallaba, la fuente quedaba con CERO chunks, peor que antes
    # de pedir la re-fragmentación. Ver también la prueba de
    # integración equivalente contra SQLite real en
    # tests/integration/test_ingestion_repositories.py.
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service.extract_source_text("p1", source.id)

    chunks_v1 = ingestion_service.fragment_source("p1", source.id)
    assert len(chunks_v1) >= 1

    chunk_repo = ingestion_service._fragment._chunk_repository
    chunk_repo.fail_replace_for_source = True
    with pytest.raises(RuntimeError):
        ingestion_service.fragment_source("p1", source.id)

    chunk_repo.fail_replace_for_source = False
    assert ingestion_service.list_chunks("p1", source.id) == chunks_v1


def test_fragment_source_uses_real_tokenizer_for_chunk_token_count_when_configured():
    # Ítem 7 de la evaluación de madurez post-8-etapas: con un
    # TokenCounter configurado, Chunk.token_count refleja SU conteo
    # (tokens_per_word=2 en el fake), no la aproximación por palabras.
    token_counter = FakeTokenCounter(tokens_per_word=2)
    document_service, _, ingestion_service = _build_services(token_counter=token_counter)
    text = "una dos tres cuatro cinco seis siete ocho nueve diez"  # 10 palabras
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = ingestion_service.fragment_source("p1", source.id)

    assert len(chunks) == 1
    assert chunks[0].token_count == 20  # 10 palabras * 2 tokens/palabra del fake
    assert token_counter.calls  # de verdad se llamó


def test_fragment_source_por_tamanio_sizes_windows_by_real_token_budget():
    # Con tokens_per_word=2, una ventana de target_tokens=20 debe
    # contener 10 palabras reales (no 20) -- confirma que split_by_size
    # usa el PRESUPUESTO de tokens del contador inyectado, no un conteo
    # de palabras fijo.
    token_counter = FakeTokenCounter(tokens_per_word=2)
    document_service, _, ingestion_service = _build_services(token_counter=token_counter)
    text = " ".join(f"palabra{i}" for i in range(40))
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/big.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/big.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy(
        "p1", "default", strategy=FragmentationStrategy.POR_TAMANIO,
        target_tokens=20, overlap_tokens=0, min_tokens=1,
    )
    chunks = ingestion_service.fragment_source("p1", source.id)

    assert len(chunks[0].text.split()) == 10  # 20 tokens / 2 tokens por palabra
    assert chunks[0].token_count == 20


def test_fragment_source_falls_back_to_word_count_when_tokenizer_unavailable():
    # Simula "sin conexión para la descarga inicial" -- la
    # fragmentación debe completarse igual, usando word_count para
    # esta corrida (ver FragmentSource._resolve_count_tokens).
    document_service, _, ingestion_service = _build_services(token_counter=FailingTokenCounter())
    text = "una dos tres cuatro cinco"
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = ingestion_service.fragment_source("p1", source.id)

    assert len(chunks) == 1
    assert chunks[0].token_count == 5  # word_count de respaldo, no un error ni un 0


def test_fragment_source_without_token_counter_uses_word_count_as_before(services):
    document_service, _, ingestion_service = services
    text = "una dos tres cuatro cinco"
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = ingestion_service.fragment_source("p1", source.id)

    assert chunks[0].token_count == 5


def test_fragment_source_documento_completo_produces_one_chunk(services):
    document_service, _, ingestion_service = services
    text = "Aviso: el horario de atención cambia a partir del lunes."
    source = document_service.register_source("p1", "Aviso", SourceType.TXT, location="/aviso.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/aviso.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "aviso", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="aviso")
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_fragment_source_por_encabezado_splits_on_markdown_headings(services):
    document_service, _, ingestion_service = services
    text = "# Sección A\ncontenido de A\n\n# Sección B\ncontenido de B\n"
    source = document_service.register_source("p1", "Manual", SourceType.MARKDOWN, location="/manual.md")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/manual.md": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "manual", strategy=FragmentationStrategy.POR_ENCABEZADO)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="manual")
    assert [c.section_title for c in chunks] == ["Sección A", "Sección B"]


def test_fragment_source_por_articulo_keeps_whole_article_in_one_chunk(services):
    # Módulo 5: reglamento -- un fragmento por artículo completo, sin
    # sub-dividir aunque exceda target_tokens (target_tokens=5 aquí,
    # muy por debajo del tamaño real de cada artículo, a propósito).
    document_service, _, ingestion_service = services
    text = (
        "Artículo 1.- Este reglamento aplica a todo el alumnado inscrito.\n"
        "Excepto quienes cuenten con beca vigente al momento de inscribirse.\n\n"
        "Artículo 2.- La inscripción debe realizarse en tiempo y forma establecidos.\n"
    )
    source = document_service.register_source("p1", "Reglamento", SourceType.TXT, location="/reglamento.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/reglamento.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy(
        "p1", "reglamento", strategy=FragmentationStrategy.POR_ARTICULO,
        target_tokens=5, overlap_tokens=0, min_tokens=0,
    )
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="reglamento")
    assert [c.section_title for c in chunks] == ["Artículo 1", "Artículo 2"]
    assert "Excepto quienes" in chunks[0].text  # el supuesto y su excepción no se separaron
    assert all(c.chunk_type == ChunkType.TEXTO for c in chunks)


def test_fragment_source_pregunta_respuesta_produces_one_chunk_per_question(services):
    document_service, _, ingestion_service = services
    text = (
        "P: ¿Cuál es la duración de la maestría?\n"
        "R: La maestría dura 4 cuatrimestres.\n\n"
        "P: ¿Hay examen de admisión?\n"
        "R: Sí, uno de conocimientos generales.\n"
    )
    source = document_service.register_source("p1", "FAQ", SourceType.TXT, location="/faq.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/faq.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "faq", strategy=FragmentationStrategy.PREGUNTA_RESPUESTA)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="faq")
    assert len(chunks) == 2
    assert all(c.chunk_type == ChunkType.PREGUNTA_RESPUESTA for c in chunks)
    assert "La maestría dura 4 cuatrimestres" in chunks[0].text
    assert "Sí, uno de conocimientos generales" in chunks[1].text


def test_fragment_source_por_tabla_marks_table_chunks_and_repeats_header(services):
    document_service, _, ingestion_service = services
    text = (
        "Programas ofertados este cuatrimestre.\n\n"
        "| Programa | Plantel |\n"
        "| --- | --- |\n"
        "| Ing. Biomédica | Mérida |\n"
        "| Ing. Industrial | Progreso |\n"
    )
    source = document_service.register_source("p1", "Catálogo", SourceType.TXT, location="/catalogo.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/catalogo.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "tabla", strategy=FragmentationStrategy.POR_TABLA)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="tabla")

    table_chunks = [c for c in chunks if c.chunk_type == ChunkType.TABLA]
    text_chunks = [c for c in chunks if c.chunk_type == ChunkType.TEXTO]
    assert len(table_chunks) == 1
    assert "Programa" in table_chunks[0].text and "Ing. Biomédica" in table_chunks[0].text
    assert len(text_chunks) == 1
    assert "Programas ofertados" in text_chunks[0].text


def test_fragment_source_por_hoja_estructurada_produces_one_chunk_per_block(services):
    # Pista B.2 del ADR-003: un chunk ChunkType.ESTRUCTURADO por cada
    # bloque de structured_blocks -- structured_content lleva el bloque
    # completo (columnas/filas nativas), no solo el texto Markdown.
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Catálogo", SourceType.XLSX, location="/catalogo.xlsx")
    ingestion_service._extract._extractor = FakeTextExtractor(
        supported_types={SourceType.XLSX},
        canned={"/catalogo.xlsx": (
            "## Programas\n\n| codigo |\n| --- |\n| ISC |\n\n## Planteles\n\n| plantel |\n| --- |\n| Mérida |",
            "xlsx", [], [],
        )},
        canned_structured={"/catalogo.xlsx": {
            "Programas": {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]},
            "Planteles": {"columnas": ["plantel"], "filas": [{"plantel": "Mérida"}]},
        }},
    )
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "catalogo", strategy=FragmentationStrategy.POR_HOJA_ESTRUCTURADA)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="catalogo")

    assert len(chunks) == 2
    assert all(c.chunk_type == ChunkType.ESTRUCTURADO for c in chunks)
    by_title = {c.section_title: c for c in chunks}
    assert by_title["Programas"].structured_content == {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}
    assert by_title["Planteles"].structured_content == {"columnas": ["plantel"], "filas": [{"plantel": "Mérida"}]}
    assert "ISC" in by_title["Programas"].text
    assert "Mérida" in by_title["Planteles"].text


def test_fragment_source_por_hoja_estructurada_handles_csv_style_block_without_headings(services):
    # CSV: structured_blocks trae una única clave fija "datos" que no
    # coincide con ningún encabezado Markdown (un CSV no tiene "##") --
    # debe usar el texto completo como mejor esfuerzo, no perder el bloque.
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Programas", SourceType.CSV, location="/programas.csv")
    ingestion_service._extract._extractor = FakeTextExtractor(
        supported_types={SourceType.CSV},
        canned={"/programas.csv": ("| codigo |\n| --- |\n| ISC |", "csv", [], [])},
        canned_structured={"/programas.csv": {"datos": {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}}},
    )
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "csv", strategy=FragmentationStrategy.POR_HOJA_ESTRUCTURADA)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="csv")

    assert len(chunks) == 1
    assert chunks[0].chunk_type == ChunkType.ESTRUCTURADO
    assert chunks[0].section_title == "datos"
    assert chunks[0].structured_content == {"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]}
    assert "ISC" in chunks[0].text


def test_fragment_source_por_hoja_estructurada_degrades_to_documento_completo_without_blocks(services):
    # Fuente sin bloques estructurados (no XLSX/CSV, o extractor sin
    # esta capacidad): se degrada a DOCUMENTO_COMPLETO -- ni falla ni
    # produce cero chunks.
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": ("contenido plano", "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy("p1", "plano", strategy=FragmentationStrategy.POR_HOJA_ESTRUCTURADA)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="plano")

    assert len(chunks) == 1
    assert chunks[0].chunk_type == ChunkType.TEXTO
    assert chunks[0].text == "contenido plano"


def test_fragment_source_falls_back_to_default_policy_then_builtin(services):
    document_service, _, ingestion_service = services
    text = "contenido corto"
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    # sin ninguna política configurada: usa la interna por defecto y no falla
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="tipo-sin-politica")
    assert len(chunks) == 1
    assert chunks[0].text == text

    # con una política "default" configurada, un tipo sin política propia la usa
    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="otro-tipo-sin-politica")
    assert len(chunks) == 1


def test_fragment_source_inherits_only_flagged_metadata(services):
    document_service, metadata_service, ingestion_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", "texto", inherited_by_chunks=True)
    metadata_service.add_field_definition("p1", schema.id, "notas_internas", "Notas", "texto", inherited_by_chunks=False)

    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus", "MERIDA")
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "notas_internas", "confidencial")

    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": ("texto de la fuente", "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)
    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = ingestion_service.fragment_source("p1", source.id, schema_id=schema.id)

    assert chunks[0].inherited_metadata == {"campus": "MERIDA"}


def test_extract_source_text_returns_none_and_saves_nothing_when_cancelled_up_front(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")

    record = ingestion_service.extract_source_text("p1", source.id, is_cancelled=lambda: True)
    assert record is None
    assert ingestion_service.get_extraction_record("p1", source.id) is None


def test_extract_source_text_returns_none_and_saves_nothing_when_cancelled_after_extraction(services):
    document_service, _, ingestion_service = services
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")

    # Se cancela justo antes de guardar (la extracción en sí ya
    # "corrió" -- el extractor no tiene puntos de control intermedios,
    # ver docstring de ExtractSourceText.execute) -- el resultado no
    # debe persistirse.
    calls = {"n": 0}

    def is_cancelled():
        calls["n"] += 1
        return calls["n"] > 1  # False la primera vez (antes de extraer), True la segunda (antes de guardar)

    record = ingestion_service.extract_source_text("p1", source.id, is_cancelled=is_cancelled)
    assert record is None
    assert ingestion_service.get_extraction_record("p1", source.id) is None


def test_fragment_source_returns_none_and_keeps_previous_chunks_when_cancelled_up_front(services):
    document_service, _, ingestion_service = services
    text = "contenido corto"
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)
    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)

    # Primero una fragmentación real, para tener fragmentos "anteriores".
    first = ingestion_service.fragment_source("p1", source.id)
    assert len(first) == 1

    # Reintentar fragmentar, pero cancelado desde el principio: no debe
    # tocar delete_for_source/save_many -- los fragmentos anteriores
    # siguen ahí tal cual.
    result = ingestion_service.fragment_source("p1", source.id, is_cancelled=lambda: True)
    assert result is None
    assert ingestion_service.list_chunks("p1", source.id) == first


def test_fragment_source_returns_none_and_does_not_persist_when_cancelled_mid_loop(services):
    document_service, _, ingestion_service = services
    text = " ".join(f"palabra{i}" for i in range(60))
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/big.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/big.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)
    ingestion_service.set_fragmentation_policy(
        "p1", "default", strategy=FragmentationStrategy.POR_TAMANIO, target_tokens=20, overlap_tokens=5, min_tokens=5,
    )

    # Se cancela justo después de armar el primer fragmento del bucle
    # (ver FragmentSource.execute: revisa is_cancelled() en cada
    # vuelta) -- debe abortar antes de llegar a guardar nada.
    calls = {"n": 0}

    def is_cancelled():
        calls["n"] += 1
        return calls["n"] > 2  # deja pasar las dos primeras revisiones (inicio + 1a vuelta)

    result = ingestion_service.fragment_source("p1", source.id, is_cancelled=is_cancelled)
    assert result is None
    assert ingestion_service.list_chunks("p1", source.id) == []


def test_fragment_source_is_idempotent_on_re_fragmentation(services):
    document_service, _, ingestion_service = services
    text = "contenido estable que no cambia entre corridas"
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)
    ingestion_service.set_fragmentation_policy("p1", "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)

    first = ingestion_service.fragment_source("p1", source.id)
    second = ingestion_service.fragment_source("p1", source.id)

    assert len(ingestion_service.list_chunks("p1", source.id)) == len(second)
    assert len(first) == len(second) == 1
    assert first[0].text == second[0].text
    # los identificadores no se prometen estables entre corridas
    assert first[0].id != second[0].id


# ---------- Pista B.1 del ADR-003: chunk padre bajo POR_ENCABEZADO ----------

def test_fragment_source_por_encabezado_creates_padre_only_for_sections_split_in_more_than_one_chunk(services):
    document_service, _, ingestion_service = services
    palabras_b = " ".join(f"palabra{i}" for i in range(1, 26))  # 25 palabras
    text = (
        "# Sección A\n"
        "contenido corto\n\n"
        "# Sección B\n"
        f"{palabras_b}\n"
    )
    source = document_service.register_source("p1", "Manual", SourceType.MARKDOWN, location="/manual.md")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/manual.md": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy(
        "p1", "manual", strategy=FragmentationStrategy.POR_ENCABEZADO,
        target_tokens=10, overlap_tokens=0, min_tokens=0,
    )
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="manual")

    padres = [c for c in chunks if c.chunk_type == ChunkType.PADRE]
    hijos_a = [c for c in chunks if c.chunk_type != ChunkType.PADRE and c.section_title == "Sección A"]
    hijos_b = [c for c in chunks if c.chunk_type != ChunkType.PADRE and c.section_title == "Sección B"]

    # Sección A cupo entera en un solo chunk -- no genera padre.
    assert len(hijos_a) == 1
    assert hijos_a[0].parent_chunk_id is None

    # Sección B se sub-dividió en más de un chunk -- sí genera padre.
    assert len(hijos_b) > 1
    assert len(padres) == 1
    padre = padres[0]
    assert padre.section_title == "Sección B"
    assert all(hijo.parent_chunk_id == padre.id for hijo in hijos_b)
    # El padre contiene la sección completa, sin fragmentar.
    assert "palabra1 " in padre.text and "palabra25" in padre.text

    # El padre nunca entra a la cadena de lectura lineal (previous/next).
    assert padre.previous_chunk_id is None
    assert padre.next_chunk_id is None


def test_fragment_source_padre_chunk_index_continues_after_all_children(services):
    document_service, _, ingestion_service = services
    palabras_b = " ".join(f"palabra{i}" for i in range(1, 26))
    text = f"# Sección única\n{palabras_b}\n"
    source = document_service.register_source("p1", "Manual", SourceType.MARKDOWN, location="/manual.md")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/manual.md": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy(
        "p1", "manual", strategy=FragmentationStrategy.POR_ENCABEZADO,
        target_tokens=10, overlap_tokens=0, min_tokens=0,
    )
    chunks = ingestion_service.fragment_source("p1", source.id, document_type_code="manual")

    hijos = [c for c in chunks if c.chunk_type != ChunkType.PADRE]
    padres = [c for c in chunks if c.chunk_type == ChunkType.PADRE]
    assert len(padres) == 1
    assert padres[0].chunk_index == len(hijos)
    assert [c.chunk_index for c in hijos] == list(range(len(hijos)))


def test_fragment_source_por_tamanio_never_creates_padre_chunks(services):
    # Ninguna estrategia salvo POR_ENCABEZADO produce jerarquía -- esto
    # confirma cero cambio de comportamiento para el resto.
    document_service, _, ingestion_service = services
    text = "una dos tres cuatro cinco seis siete ocho nueve diez once doce"
    source = document_service.register_source("p1", "Ficha", SourceType.TXT, location="/x.txt")
    ingestion_service._extract._extractor = FakeTextExtractor(canned={"/x.txt": (text, "fake", [], [])})
    ingestion_service.extract_source_text("p1", source.id)

    ingestion_service.set_fragmentation_policy(
        "p1", "default", strategy=FragmentationStrategy.POR_TAMANIO,
        target_tokens=5, overlap_tokens=0, min_tokens=0,
    )
    chunks = ingestion_service.fragment_source("p1", source.id)
    assert len(chunks) > 1
    assert all(c.chunk_type != ChunkType.PADRE for c in chunks)
    assert all(c.parent_chunk_id is None for c in chunks)
