"""Puertos del contexto RAG. Implementados en infrastructure
(ADR-001, seccion 4: domain nunca importa un SDK concreto -- ni
qdrant_client ni fastembed aparecen aqui, solo en los adaptadores).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import DEFAULT_COLLECTION_NAME, IndexInfo, VectorPoint, VectorSearchHit


class EmbeddingProvider(ABC):
    """Convierte texto en vectores. El adaptador por defecto (Etapa 4
    nucleo) usa un modelo local via FastEmbed, sin API keys ni costo
    por uso -- coherente con el principio local-primero de ADR-001."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identificador corto del proveedor (p. ej. "fastembed"), no
        del modelo. Se guarda junto con model_name en IndexInfo para
        poder distinguir "mismo modelo, otro proveedor" si algun dia
        se agrega uno nuevo."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Devuelve un vector por texto de entrada, en el mismo orden.
        Este es el lado "pasaje/documento" -- el que usa IndexSource
        para embeber los Chunk que se suben al VectorStore. Debe
        lanzar EmbeddingProviderError si el proveedor falla (p. ej. sin
        red para descargar el modelo la primera vez)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embebe una consulta de búsqueda (el lado "pregunta" de
        SemanticSearch). Por defecto delega en embed_texts -- correcto
        para modelos simétricos, donde una consulta y un pasaje se
        embeben de la misma forma (p. ej. el paraphrase-multilingual-
        MiniLM-L12-v2 por defecto de esta iteración).

        Los adaptadores de modelos ASIMÉTRICOS ("pregunta busca
        pasaje", p. ej. la familia intfloat/e5) deben sobreescribir
        este método -- esos modelos se entrenaron esperando un prefijo
        distinto en cada lado ("query: " / "passage: "); si se les
        pasa la consulta cruda, no se obtiene el beneficio para el que
        fueron entrenados y el resultado puede ser peor que con un
        modelo simétrico, no mejor. Ver
        infrastructure.embeddings.fastembed_provider para el adaptador
        que sí distingue los dos lados."""
        [vector] = self.embed_texts([text])
        return vector


class VectorStore(ABC):
    """Indice vectorial por proyecto (Qdrant en modo local por
    defecto). Cada metodo recibe project_id explicitamente -- el
    adaptador concreto resuelve la ruta/aislamiento por proyecto
    igual que los repositorios SQLAlchemy resuelven su project.db.

    `collection` (Fase 3 del diseno de multimodalidad nativa, RAG 3):
    todos los metodos aceptan un nombre de coleccion explicito,
    keyword-only, con DEFAULT_COLLECTION_NAME ("chunks") como valor por
    defecto -- ningun llamador existente antes de esta ronda pasa este
    parametro, asi que su comportamiento no cambia. Se promovio aqui,
    al puerto abstracto, porque ya existia como parametro propio del
    adaptador concreto QdrantLocalVectorStore desde la Fase 1 -- sin
    esto, application (IndexImageSource/SemanticSearchImages) habria
    tenido que depender del adaptador concreto para poder pedir la
    coleccion de imagenes, violando ADR-001, seccion 4 (application
    nunca importa infrastructure)."""

    @abstractmethod
    def ensure_collection(
        self, project_id: str, vector_size: int, *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        """Crea la coleccion si no existe. Si ya existe con otra
        dimension, debe lanzar EmbeddingDimensionMismatchError -- no
        se puede mezclar vectores de dos modelos distintos en el
        mismo indice sin reindexar todo el proyecto."""
        ...

    @abstractmethod
    def upsert(
        self, project_id: str, points: list[VectorPoint], *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> None: ...

    @abstractmethod
    def delete_for_source(
        self, project_id: str, source_id: str, *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        """Borra todos los puntos cuyo payload tenga ese source_id --
        paso previo a volver a indexar una fuente (misma logica
        idempotente que ChunkRepository.delete_for_source de la
        Etapa 3: los ids de Chunk no se prometen estables entre
        corridas, asi que hay que limpiar antes de insertar)."""
        ...

    @abstractmethod
    def search(
        self, project_id: str, query_vector: list[float], limit: int,
        source_id: Optional[str] = None, *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> list[VectorSearchHit]: ...

    @abstractmethod
    def count(self, project_id: str, *, collection: str = DEFAULT_COLLECTION_NAME) -> int: ...


class Reranker(ABC):
    """Reordena candidatos ya recuperados segun su relevancia real para
    la consulta -- a diferencia de RRF (ver
    application.rag.queries.hybrid_search), que solo combina RANGOS de
    listas ya existentes sin mirar ningun texto, un reranker si examina
    la consulta junto con el texto de cada candidato (tipicamente con un
    modelo cross-encoder) para calcular un puntaje de relevancia nuevo.

    ADR-003, Pista A.2: paso OPCIONAL despues de la fusion RRF -- quien
    no configure ningun Reranker sigue viendo exactamente el mismo
    comportamiento que antes de esa ronda (ver
    HybridSearch.execute, parametro `rerank`, y
    domain.rag.exceptions.RerankerUnavailableError). Debe ser un modelo
    LOCAL (mismo principio "local-primero" de ADR-001/ADR-003, sin API
    de pago) -- ver infrastructure.rerankers.fastembed_cross_encoder
    para el adaptador de referencia."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def score(self, query_text: str, passages: list[str]) -> list[float]:
        """Un puntaje de relevancia por cada texto de `passages`, en el
        mismo orden -- mas alto es mas relevante. Es un puntaje crudo,
        sin rango numerico fijo garantizado (depende del modelo
        concreto): solo sirve para reordenar este mismo lote, nunca
        para compararse contra el score de fusion RRF ni contra otro
        Reranker. Debe lanzar RerankerError si el modelo no pudo
        calcular los puntajes (p. ej. sin red para descargarlo la
        primera vez)."""
        ...

    def ensure_ready(self) -> None:
        """Ronda 105b (P1): carga el modelo AHORA y lanza RerankerError si no
        puede (sin esperar al primer score). Por defecto no hace nada: un
        reranker sin carga diferida ya está listo."""
        return None

    @property
    def is_loaded(self) -> bool:
        """Ronda 105b (P1): True si el modelo está cargado y verificado (no
        solo configurado). Por defecto True (sin carga diferida)."""
        return True


class ImageEmbeddingProvider(ABC):
    """Convierte imágenes en vectores, en el mismo espacio semántico que
    su texto de consulta (modelos tipo CLIP) -- puerto hermano de
    EmbeddingProvider, pensado para la Fase 1 del diseño de
    multimodalidad nativa (ver docs proyecto/RAG_STUDIO_Diseno_
    Ejecutable_RAG3_Multimodalidad.docx, sección 3.2). No existe
    todavía ningún adaptador que lo consuma en el pipeline de
    ingestión/búsqueda -- este puerto y su adaptador de referencia
    (infrastructure.embeddings.fastembed_image_provider) son la
    preparación de infraestructura; conectarlo a IndexSource/
    SemanticSearch es trabajo de fases posteriores, no de esta.

    Deliberadamente NO es una alternativa a EmbeddingProvider ni un
    tercer puerto genérico "de contenido" -- son modelos distintos
    (texto vs. imagen), con costos de carga distintos, y proyectos que
    nunca usan fuentes de imagen no deberían tener que instanciar ni
    descargar nada de este puerto (mismo criterio de "capacidad
    opcional" que Reranker)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identificador corto del proveedor (p. ej. "fastembed"), mismo
        criterio que EmbeddingProvider.provider_name -- se guarda junto
        con model_name para poder distinguir "mismo modelo, otro
        proveedor" si algún día se agrega uno nuevo."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def embed_images(self, image_paths: list[str]) -> list[list[float]]:
        """Devuelve un vector por imagen de entrada, en el mismo orden.
        Recibe rutas de archivo (no bytes en memoria) porque el origen
        real es siempre un archivo ya copiado por SourceFileStore a
        sources/original/ -- no hace falta cargar la imagen completa en
        el llamador para pedir su vector. Debe lanzar
        EmbeddingProviderError si el proveedor falla (p. ej. sin red
        para descargar el modelo la primera vez, o un archivo no es una
        imagen válida) -- mismo contrato de errores que
        EmbeddingProvider.embed_texts."""
        ...

    def embed_query_text(self, text: str) -> list[float]:
        """Embebe una consulta en lenguaje natural al MISMO espacio
        vectorial que `embed_images` -- el lado "texto busca imagen" de
        la Fase 3 del diseño de multimodalidad nativa (RAG 3, ver
        application.rag.queries.semantic_search_images.
        SemanticSearchImages). Requiere un modelo tipo CLIP con un
        codificador de texto pareado en el mismo espacio semántico; no
        todos los modelos de imagen lo tienen (p. ej. Qdrant/resnet50-
        onnx solo sirve para "imagen busca imagen").

        Método CONCRETO, no abstracto -- a propósito, mismo criterio
        que EmbeddingProvider.embed_query: por defecto lanza
        NotImplementedError con un mensaje claro, para que un
        adaptador de imagen sin codificador de texto pareado siga
        siendo instanciable y utilizable para `embed_images` (que sí es
        su capacidad central) sin verse obligado a implementar algo que
        no tiene sentido para él. Los adaptadores que sí soportan esta
        capacidad (ver infrastructure.embeddings.fastembed_image_provider.
        FastEmbedImageProvider, para el modelo por defecto) la
        sobreescriben."""
        raise NotImplementedError(
            f"{type(self).__name__} no soporta embeber consultas de texto en el "
            "espacio de imágenes -- falta un codificador de texto pareado para "
            f"el modelo {self.model_name!r}."
        )


class IndexInfoRepository(ABC):
    @abstractmethod
    def save(self, info: IndexInfo) -> None: ...

    @abstractmethod
    def get(self, project_id: str) -> Optional[IndexInfo]: ...
