"""Excepciones del contexto RAG."""
from __future__ import annotations


class RagDomainError(Exception):
    """Base de las excepciones del contexto RAG."""


class EmbeddingProviderError(RagDomainError):
    """El proveedor de embeddings no pudo generar vectores (p. ej. sin
    red para descargar el modelo la primera vez, o el modelo no esta
    disponible)."""


class EmbeddingDimensionMismatchError(RagDomainError):
    """El indice vectorial del proyecto ya existe con una dimension
    distinta a la del modelo de embeddings actual. Mezclar vectores de
    dos modelos en la misma coleccion produce busquedas sin sentido;
    hay que reindexar todo el proyecto con un modelo consistente."""


class EmptyIndexError(RagDomainError):
    """Se intento buscar en un proyecto que todavia no tiene ningun
    fragmento indexado."""


class EmbeddingProfileComparisonUnavailableError(RagDomainError):
    """Se lanza al llamar RagService.compare_profiles() cuando el
    servicio se construyo sin `embedding_provider_factory` -- el mismo
    patron de "capacidad opcional" que OcrEngine en PdfTextExtractor:
    quien no necesita comparar modelos (la mayoria de las pruebas, por
    ejemplo) no tiene que construir ni pasar nada de mas."""

    def __init__(self):
        super().__init__(
            "El comparador de modelos de embeddings no esta disponible: "
            "RagService se construyo sin embedding_provider_factory."
        )


class RerankerError(RagDomainError):
    """El reranker no pudo calcular puntajes de relevancia (p. ej. sin
    red para descargar el modelo la primera vez, o el modelo no esta
    disponible) -- mismo criterio que EmbeddingProviderError."""


class RerankingRequiredUnavailableError(RagDomainError):
    """Ronda 105b (P1, alternativa B estricta, autorizada por NEXOM): el
    proyecto tiene «Reranking en el agente: Activado» y el modelo de
    reranking no está disponible o no se pudo cargar. Se falla de forma
    explícita (Simulador y Runtime) en vez de responder sin reranking: la
    configuración efectiva debe ser la misma en pruebas y despliegue."""


class RerankerUnavailableError(RagDomainError):
    """Se lanza al pedir rerank=True en HybridSearch.execute/
    RagService.search_hybrid cuando no se configuro ningun Reranker --
    mismo patron de "capacidad opcional" que SourceFilterUnavailableError/
    EmbeddingProfileComparisonUnavailableError: sin un Reranker
    configurado no hay puntajes que calcular, asi que se prefiere
    fallar con un mensaje claro en vez de ignorar el pedido en
    silencio y devolver el orden de fusion RRF sin avisar."""

    def __init__(self):
        super().__init__(
            "El reranking real no esta disponible: no se configuro ningun "
            "Reranker para este servicio."
        )


class NotAnImageSourceError(RagDomainError):
    """Se lanza al llamar RagService.index_image_source()/IndexImageSource
    sobre una fuente que existe pero cuyo source_type no es
    SourceType.IMAGEN_NATIVA -- a diferencia de IndexSource (sirve para
    cualquier tipo de fuente), IndexImageSource es específico de
    imágenes nativas (Fase 3 de multimodalidad nativa, RAG 3): no tiene
    sentido pedirle que indexe, por ejemplo, un PDF."""

    def __init__(self, source_id: str, actual_type: str):
        super().__init__(
            f"La fuente {source_id!r} no es una imagen nativa (tipo actual: "
            f"{actual_type!r}) -- IndexImageSource solo indexa fuentes "
            "SourceType.IMAGEN_NATIVA."
        )
        self.source_id = source_id


class ImageSearchUnavailableError(RagDomainError):
    """Se lanza al llamar RagService.index_image_source()/search_images()
    cuando el servicio se construyó sin `image_embedding_provider` --
    mismo patrón de "capacidad opcional" que
    EmbeddingProfileComparisonUnavailableError/RerankerUnavailableError:
    quien no tiene fuentes de imagen (la mayoría de los proyectos hoy)
    no tiene que pagar el costo de configurar ni descargar un modelo de
    imagen para poder usar el resto de RagService.

    `index_image_source()` en particular tiene una segunda dependencia
    real: a diferencia de IndexSource, IndexImageSource necesita leer el
    Source original directamente (ver Ronda 65, punto 221), así que
    también requiere `source_repository` -- si se configuró
    `image_embedding_provider` pero no `source_repository`,
    `search_images()` sí funciona (source_repository ahí solo habilita
    los filtros opcionales only_usable_sources/max_access_level, ver
    SourceFilterUnavailableError) pero `index_image_source()` no."""

    def __init__(self, missing: str = "image_embedding_provider"):
        super().__init__(
            f"La indexación/búsqueda de imágenes no está disponible: RagService "
            f"se construyó sin {missing}."
        )


class SourceFilterUnavailableError(RagDomainError):
    """Se lanza al pedir only_usable_sources=True o max_access_level=...
    (Pista B.3 del ADR-003) en RagService.search()/search_text()/
    search_hybrid() cuando el servicio se construyo sin
    `source_repository` -- mismo patron de "capacidad opcional" que
    EmbeddingProfileComparisonUnavailableError: ambos filtros necesitan
    resolver el Source de cada chunk para decidir si pasa (vigencia/
    validacion en un caso, access_level en el otro), asi que sin ese
    repositorio se prefiere fallar con un mensaje claro en vez de
    ignorar el filtro en silencio (lo que dejaria pasar documentos
    rechazados/vencidos/no validados, o por encima del nivel de acceso
    autorizado, sin que quien llama se de cuenta)."""

    def __init__(self):
        super().__init__(
            "Un filtro basado en el estado de la fuente (only_usable_sources o "
            "max_access_level) no esta disponible: RagService se construyo sin "
            "source_repository."
        )
