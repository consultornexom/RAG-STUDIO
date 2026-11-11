"""Fachada de application para el contexto RAG (Etapa 4 -- núcleo)."""
from __future__ import annotations

from collections.abc import Collection
from typing import Callable, Optional

from pydantic import ValidationError

from domain.documents.entities import AccessLevel
from domain.documents.ports import SourceRepository
from domain.ingestion.ports import ChunkRepository
from domain.rag.entities import DEFAULT_MIN_RELEVANT_SCORE, IndexInfo, has_low_relevance
from domain.rag.exceptions import EmbeddingProfileComparisonUnavailableError, ImageSearchUnavailableError
from domain.rag.ports import EmbeddingProvider, ImageEmbeddingProvider, IndexInfoRepository, Reranker, VectorStore
from domain.rag.structured_query import StructuredAggregation, StructuredFilter, StructuredQueryResult

from .commands.index_image_source import IndexImageSource
from .commands.index_source import IndexSource
from .queries.compare_embedding_profiles import CompareEmbeddingProfiles, ProfileComparisonResult
from .queries.get_index_info import GetIndexInfo
from .queries.hybrid_search import HybridSearch
from .queries.semantic_search import SemanticSearch, SemanticSearchResult
from .queries.semantic_search_images import ImageSearchResult, SemanticSearchImages
from .queries.structured_query import StructuredQuery
from .queries.text_search import TextSearch


class RagService:
    MIN_RELEVANT_SCORE = DEFAULT_MIN_RELEVANT_SCORE

    def __init__(
        self,
        chunk_repository: ChunkRepository,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        index_info_repository: IndexInfoRepository,
        embedding_provider_factory: Optional[Callable[[str], EmbeddingProvider]] = None,
        available_embedding_profiles: Optional[list[str]] = None,
        source_repository: Optional[SourceRepository] = None,
        reranker: Optional[Reranker] = None,
        image_embedding_provider: Optional[ImageEmbeddingProvider] = None,
    ):
        # Guardado para exponer embed_query/embed_texts (ver más abajo):
        # Etapa 5 (emparejamiento semántico de intención,
        # domain.conversational.intent_matching) reutiliza el mismo
        # EmbeddingProvider que ya usan indexación/búsqueda, en vez de
        # construir un segundo modelo -- un solo proveedor de embeddings
        # por proyecto, coherente con ADR-001.
        self._embedding_provider = embedding_provider
        # embedding_provider_factory/available_embedding_profiles/
        # source_repository son opcionales (capacidad extra, igual que
        # ocr_engine en PdfTextExtractor): quien no necesita comparar
        # modelos o filtrar por vigencia --la mayoría de las pruebas,
        # por ejemplo-- no tiene que construir ni pasar nada de más, y
        # el comportamiento existente no cambia.
        self._index_source = IndexSource(
            chunk_repository, embedding_provider, vector_store, index_info_repository
        )
        self._search = SemanticSearch(
            embedding_provider, vector_store, chunk_repository, source_repository=source_repository,
        )
        # TextSearch/HybridSearch no necesitan capacidad opcional propia
        # (a diferencia del comparador de modelos o el OCR): no exigen
        # ninguna dependencia nueva -- BM25 es puro y solo necesita el
        # ChunkRepository que RagService ya recibe siempre. Siempre
        # están disponibles, igual que `search`.
        self._text_search = TextSearch(chunk_repository, source_repository=source_repository)
        # reranker (ADR-003, Pista A.2): igual que embedding_provider_factory/
        # source_repository, capacidad opcional -- quien no lo pase no ve
        # ningun cambio de comportamiento respecto a antes de esta ronda.
        self._hybrid_search = HybridSearch(self._search, self._text_search, reranker=reranker)
        # StructuredQuery (Pista B.2b del ADR-003): a diferencia de lo
        # que decía este comentario antes de la auditoría posterior a
        # la Ronda 76, SÍ recibe ahora `source_repository` -- mismo
        # criterio que TextSearch, para poder ofrecer
        # only_usable_sources/max_access_level (ver docstring de
        # StructuredQuery.execute sobre por qué esta consulta se había
        # quedado sin ese filtro).
        self._structured_query = StructuredQuery(chunk_repository, source_repository=source_repository)
        self._get_index_info = GetIndexInfo(index_info_repository)
        self._available_profiles = list(available_embedding_profiles or [])
        self._compare_profiles = (
            CompareEmbeddingProfiles(chunk_repository, embedding_provider_factory)
            if embedding_provider_factory is not None else None
        )
        # image_embedding_provider (Fase 3 de multimodalidad nativa, RAG
        # 3): capacidad opcional, mismo patrón que reranker/
        # embedding_provider_factory -- un proyecto sin fuentes de
        # imagen (la mayoría, hoy) no tiene que construir ni descargar
        # nada de este modelo. Ver ImageSearchUnavailableError -- nota
        # ahí sobre por qué index_image_source() también necesita
        # source_repository, a diferencia de search_images().
        self._has_image_embedding_provider = image_embedding_provider is not None
        self._index_image_source = (
            IndexImageSource(source_repository, chunk_repository, image_embedding_provider, vector_store)
            if image_embedding_provider is not None and source_repository is not None else None
        )
        self._search_images = (
            SemanticSearchImages(
                image_embedding_provider, vector_store, chunk_repository, source_repository=source_repository,
            )
            if image_embedding_provider is not None else None
        )

    def index_source(self, project_id: str, source_id: str) -> int:
        return self._index_source.execute(project_id, source_id)

    def index_image_source(self, project_id: str, source_id: str) -> int:
        """Indexa (o reindexa) la imagen de una fuente SourceType.
        IMAGEN_NATIVA -- hermano de `index_source`, ver
        application.rag.commands.index_image_source.IndexImageSource
        para el porqué de leer el Source directamente en vez de partir
        de Chunk ya fragmentados.

        Lanza ImageSearchUnavailableError si este RagService se
        construyó sin `image_embedding_provider` (o sin
        `source_repository`, que este comando en particular también
        necesita -- ver docstring de esa excepción). Lanza
        SourceNotFoundError/NotAnImageSourceError igual que el comando
        subyacente."""
        if self._index_image_source is None:
            missing = "image_embedding_provider" if not self._has_image_embedding_provider else "source_repository"
            raise ImageSearchUnavailableError(missing)
        return self._index_image_source.execute(project_id, source_id)

    def search(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        expand_to_parent: bool = False, max_access_level: Optional[AccessLevel] = None,
    ) -> list[SemanticSearchResult]:
        """only_usable_sources=True excluye resultados cuya fuente no
        esté VALIDADO y vigente (Source.is_usable_for_responses) -- ver
        domain.rag.exceptions.SourceFilterUnavailableError si RagService
        se construyó sin source_repository. Documento maestro,
        "supuestos prohibidos": no usar documentos rechazados, vencidos
        o no validados.

        expand_to_parent=True (Pista B.1 del ADR-003, docs proyecto/
        RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 6):
        cuando un resultado proviene de un chunk con `parent_chunk_id`
        (hoy, solo posible bajo la estrategia POR_ENCABEZADO cuando una
        sección se sub-dividió en más de un fragmento), se adjunta
        también el chunk PADRE completo en
        `SemanticSearchResult.parent_chunk` -- el chunk encontrado
        (`.chunk`) nunca se reemplaza, para no perder cuál fue el
        extracto puntual que de verdad coincidió con la consulta.
        Capacidad aditiva: sin pedirlo, el comportamiento no cambia.

        max_access_level (Pista B.3 del ADR-003, docs proyecto/
        RAG_STUDIO_Propuesta_B3_Control_Acceso.docx): excluye resultados
        cuya fuente tenga un Source.access_level más restrictivo que
        este techo -- mismo mecanismo de "capacidad opcional" que
        only_usable_sources (misma excepción si no hay
        source_repository configurado). None (por defecto) significa
        sin techo, comportamiento actual sin cambios."""
        return self._search.execute(
            project_id, query_text, limit=limit, source_id=source_id,
            only_usable_sources=only_usable_sources, expand_to_parent=expand_to_parent,
            max_access_level=max_access_level,
        )

    def search_images(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        max_access_level: Optional[AccessLevel] = None,
    ) -> list[ImageSearchResult]:
        """Búsqueda por similitud visual ("texto busca imagen", Fase 3
        de multimodalidad nativa) sobre las imágenes nativas indexadas
        del proyecto -- espacio vectorial separado de `search`
        (imágenes vs. texto no son comparables, ver Ronda 36 sobre el
        riesgo de fusionar espacios distintos con RRF): no existe un
        `search_hybrid` que combine ambos.

        only_usable_sources/max_access_level: mismo significado que en
        `search`. Lanza ImageSearchUnavailableError si este RagService
        se construyó sin `image_embedding_provider`."""
        if self._search_images is None:
            raise ImageSearchUnavailableError()
        return self._search_images.execute(
            project_id, query_text, limit=limit, source_id=source_id,
            only_usable_sources=only_usable_sources, max_access_level=max_access_level,
        )

    def search_text(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        expand_to_parent: bool = False, max_access_level: Optional[AccessLevel] = None,
        source_ids: Optional[Collection[str]] = None, use_hierarchy: bool = True,
    ) -> list[SemanticSearchResult]:
        """Búsqueda textual por palabra clave (BM25, ver
        domain.rag.text_search) -- complemento de `search` (semántica):
        no necesita índice vectorial ni haber indexado la fuente, se
        calcula bajo demanda sobre los fragmentos ya fragmentados. Los
        scores de este método NO son comparables numéricamente con los
        de `search` (escalas distintas -- BM25 no está acotado a
        [0, 1]).

        expand_to_parent/max_access_level: ver `search` -- mismo
        significado."""
        return self._text_search.execute(
            project_id, query_text, limit=limit, source_id=source_id,
            only_usable_sources=only_usable_sources, expand_to_parent=expand_to_parent,
            max_access_level=max_access_level, source_ids=source_ids, use_hierarchy=use_hierarchy,
        )

    def search_hybrid(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        rerank: bool = False, expand_to_parent: bool = False,
        max_access_level: Optional[AccessLevel] = None,
        source_ids: Optional[Collection[str]] = None,
        use_hierarchy: bool = True,
    ) -> list[SemanticSearchResult]:
        """Combina `search` y `search_text` con Reciprocal Rank Fusion
        (ver application.rag.queries.hybrid_search para el porqué de
        RRF en vez de promediar scores). Los scores devueltos son el
        score de fusión (suma de 1/(60+rango)), no una similitud ni un
        BM25 -- solo sirven para ordenar este resultado combinado entre
        sí, no para comparar contra `search`/`search_text`.

        rerank=True (ADR-003, Pista A.2) reordena los candidatos
        fusionados con el Reranker real configurado al construir este
        RagService -- en ese caso los scores devueltos son los del
        Reranker, no el score de fusión RRF. Lanza
        RerankerUnavailableError si se pide sin haber configurado
        ninguno (ver `has_reranker`).

        expand_to_parent/max_access_level: ver `search` -- mismo
        significado, aplicados sobre los candidatos de ambos métodos
        antes de fusionar/reordenar. `SimulateConversation` -- el motor
        conversacional real, tanto del Simulador de escritorio como de
        `POST /projects/{id}/messages` -- llama a este método con el
        techo de acceso del canal que autenticó la solicitud (Pista B.3
        del ADR-003)."""
        return self._hybrid_search.execute(
            project_id, query_text, limit=limit, source_id=source_id,
            only_usable_sources=only_usable_sources, rerank=rerank, expand_to_parent=expand_to_parent,
            max_access_level=max_access_level, source_ids=source_ids, use_hierarchy=use_hierarchy,
        )

    def query_structured(
        self, project_id: str,
        filters: Optional[list[StructuredFilter]] = None,
        aggregation: Optional[StructuredAggregation] = None,
        source_id: Optional[str] = None,
        only_usable_sources: bool = False,
        max_access_level: Optional[AccessLevel] = None,
    ) -> StructuredQueryResult:
        """Pista B.2b del ADR-003 (docs proyecto/
        RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx, sección 3.3):
        filtros y agregaciones deterministas sobre los chunks
        ChunkType.ESTRUCTURADO del proyecto (o de una sola fuente, si
        se pasa `source_id`) -- sin LLM, sin SQL libre, DSL cerrado
        (ver domain.rag.structured_query). B.2c (exponer esto por HTTP
        al agente conversacional externo) queda deliberadamente fuera
        de esta ronda -- ver sección 4 del documento de diseño: hoy
        ninguna consulta de RagService está expuesta por HTTP, y
        exponer esta sería el primer caso, con el mismo peso de
        decisión de contrato ya reconocido para B.3.

        only_usable_sources/max_access_level: mismo significado que en
        `search` -- ver StructuredQuery.execute (auditoría posterior a
        la Ronda 76): antes de esa ronda, esta vía nunca aplicaba
        ninguno de los dos filtros, a diferencia de las otras tres
        (semántica, textual, híbrida). `SimulateConversation` ya los
        fuerza en la vía estructurada, igual que en la semántica."""
        return self._structured_query.execute(
            project_id, filters=filters, aggregation=aggregation, source_id=source_id,
            only_usable_sources=only_usable_sources, max_access_level=max_access_level,
        )

    def query_structured_from_text(
        self, project_id: str, filters_text: str = "",
        aggregation_function: str = "", aggregation_column: str = "", group_by: str = "",
        source_id: Optional[str] = None,
        only_usable_sources: bool = False,
        max_access_level: Optional[AccessLevel] = None,
    ) -> StructuredQueryResult:
        """Conveniencia para ui/ingestion/panel.py (sección "Datos
        estructurados" del Laboratorio RAG): construye los
        StructuredFilter/StructuredAggregation de `query_structured` a
        partir de texto plano, para que ese panel -- que por regla
        propia solo llama a application, nunca a domain directamente --
        no tenga que importar domain.rag.structured_query.

        `filters_text`: una comparación por línea, "columna operador
        valor" (p. ej. "plantel == Mérida"); líneas vacías se ignoran.
        `aggregation_function` vacío significa "sin agregación" -- las
        otras tres opciones de agregación se ignoran en ese caso.
        Lanza ValueError con un mensaje claro (no la ValidationError
        cruda de pydantic) si una línea de filtro no tiene exactamente
        3 partes, si el operador no es uno de los soportados, o si la
        función de agregación pedida no es una de las soportadas."""
        filters = _parse_filters_text(filters_text)
        aggregation = None
        if aggregation_function.strip():
            try:
                aggregation = StructuredAggregation(
                    function=aggregation_function.strip(),
                    column=aggregation_column.strip() or None,
                    group_by=group_by.strip() or None,
                )
            except ValidationError as exc:
                raise ValueError(f"Agregación inválida: {exc}") from exc
        return self._structured_query.execute(
            project_id, filters=filters, aggregation=aggregation, source_id=source_id,
            only_usable_sources=only_usable_sources, max_access_level=max_access_level,
        )

    @property
    def has_reranker(self) -> bool:
        """True si este RagService se construyó con un Reranker real
        configurado -- pensado para que la UI sepa si tiene sentido
        ofrecer la casilla "Reranking real" (Laboratorio RAG) sin tener
        que intentar la búsqueda primero y capturar
        RerankerUnavailableError."""
        return self._hybrid_search.has_reranker

    @property
    def reranker_model_name(self) -> Optional[str]:
        """Ronda 102 (C4): nombre del modelo de reranking configurado, para
        mostrar en el Simulador cuál intervino. None si no hay ninguno."""
        return self._hybrid_search.reranker_model_name

    @property
    def has_image_search(self) -> bool:
        """True si este RagService se construyó con un
        image_embedding_provider real -- mismo propósito que
        `has_reranker`: que la UI sepa si tiene sentido ofrecer
        búsqueda/indexación de imágenes sin tener que intentarlo primero
        y capturar ImageSearchUnavailableError."""
        return self._has_image_embedding_provider

    def get_index_info(self, project_id: str) -> Optional[IndexInfo]:
        return self._get_index_info.execute(project_id)

    def embed_query(self, text: str) -> list[float]:
        """Embebe un texto del lado "consulta" del proveedor de
        embeddings vigente del proyecto. Expuesto para que otros
        contextos de Etapas 5+ (hoy: emparejamiento semántico de
        intención, ver domain.conversational.intent_matching) puedan
        reusar el mismo modelo sin construir uno nuevo ni que
        `application.conversational` dependa de `infrastructure`
        directamente. Puede lanzar EmbeddingProviderError (p. ej. sin
        red para descargar el modelo la primera vez)."""
        return self._embedding_provider.embed_query(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Igual que `embed_query`, pero del lado "documento/pasaje" y
        en lote -- ver `embed_query` para el porqué de exponer esto."""
        return self._embedding_provider.embed_texts(texts)

    def has_low_relevance(
        self, results: list[SemanticSearchResult], min_score: float = DEFAULT_MIN_RELEVANT_SCORE,
    ) -> bool:
        """True si `results` no esta vacio pero ninguno de sus scores
        alcanza `min_score` -- ver domain.rag.entities.has_low_relevance
        para el porque de este umbral. Pensado para que la UI muestre
        una advertencia sin tener que reimplementar la logica de
        umbral en cada lugar donde se llama a `search`."""
        return has_low_relevance((r.score for r in results), min_score=min_score)

    def available_embedding_profiles(self) -> list[str]:
        """Perfiles de embeddings conocidos (p. ej. "simetrico",
        "asimetrico_e5_large") para llenar selectores en la UI, sin
        que esta capa importe infrastructure.embeddings.fastembed_provider
        directamente (ADR-001, sección 4) -- app/bootstrap.py es quien
        pasa la lista real al construir RagService. Lista vacía si no
        se configuró ninguna (compare_profiles tampoco estará
        disponible en ese caso)."""
        return list(self._available_profiles)

    def compare_profiles(
        self, project_id: str, query_text: str, profile_a: str, profile_b: str,
        source_id: Optional[str] = None, limit: int = 5,
    ) -> tuple[ProfileComparisonResult, ProfileComparisonResult]:
        """Corre la misma consulta con dos perfiles de embeddings
        distintos y devuelve los resultados de cada uno -- ver
        application.rag.queries.compare_embedding_profiles para el
        porqué de calcularlo en memoria en vez de mantener dos índices
        Qdrant paralelos. Lanza EmbeddingProfileComparisonUnavailableError
        si RagService se construyó sin embedding_provider_factory."""
        if self._compare_profiles is None:
            raise EmbeddingProfileComparisonUnavailableError()
        return self._compare_profiles.execute(
            project_id, query_text, profile_a, profile_b, source_id=source_id, limit=limit,
        )


def _parse_filters_text(text: str) -> list[StructuredFilter]:
    """Ver `RagService.query_structured_from_text`: una comparación por
    línea ("columna operador valor"), líneas vacías ignoradas."""
    filters: list[StructuredFilter] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            raise ValueError(
                f"Filtro inválido: {line!r} -- se espera 'columna operador valor' "
                "(p. ej. 'plantel == Mérida')."
            )
        column, operator, value = parts
        try:
            filters.append(StructuredFilter(column=column, operator=operator, value=value))
        except ValidationError as exc:
            raise ValueError(
                f"Filtro inválido: {line!r} -- operador no soportado (usa ==, !=, >, >=, <, <= o contains)."
            ) from exc
    return filters
