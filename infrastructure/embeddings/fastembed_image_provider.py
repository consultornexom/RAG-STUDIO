"""Adaptador ImageEmbeddingProvider sobre el paquete `fastembed`
(modelo ONNX local, sin API keys ni costo por uso) -- puerto hermano de
FastEmbedEmbeddingProvider (ver ese modulo para el patron de carga
perezosa/cache que este archivo reutiliza sin cambios de fondo).
Implementa el puerto domain.rag.ports.ImageEmbeddingProvider.

Fase 1 del diseno de multimodalidad nativa (ver docs proyecto/
RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx, seccion 3.2):
este adaptador NO esta conectado todavia a IndexSource ni a ningun
flujo de busqueda -- es la pieza de infraestructura que las fases
posteriores (2 y 3 del diseno) van a consumir.

Modelo por defecto: "Qdrant/clip-ViT-B-32-vision" (512 dimensiones,
~0.34 GB) -- el lado "vision" de un modelo CLIP ya empaquetado en
fastembed (ver ImageEmbedding.list_supported_models()). Se eligio un
modelo CLIP, y no cualquiera de los otros modelos de vision disponibles
(p. ej. Qdrant/resnet50-onnx), porque CLIP comparte espacio semantico
con un modelo de texto hermano ("Qdrant/clip-ViT-B-32-text" en
fastembed.TextEmbedding) -- condicion necesaria para que una fase
posterior pueda buscar imagenes a partir de una consulta en lenguaje
natural (SemanticSearchImages, Fase 3 del diseno), sin la cual esta
Fase 1 seria una pieza aislada e inutil para el objetivo real del
proyecto. ResNet50, por contraste, solo sirve para "imagen busca
imagen", no para "texto busca imagen".

Limitacion importante, igual que FastEmbedEmbeddingProvider: el modelo
se descarga de Hugging Face la primera vez que se usa. Sin conexion a
internet en ese primer uso, embed_images lanza EmbeddingProviderError.

embed_query_text (Fase 3 del diseno de multimodalidad nativa): carga
perezosamente un SEGUNDO modelo, el lado "texto" pareado del CLIP
elegido arriba ("Qdrant/clip-ViT-B-32-text", tambien 512 dimensiones,
confirmado presente en fastembed.TextEmbedding.list_supported_models())
-- son dos modelos ONNX independientes que comparten espacio semantico
por como se entrenaron, no un solo modelo con dos modos. Solo se
descarga/carga si de verdad se llama a embed_query_text (SemanticSearchImages);
quien solo indexa imagenes (embed_images) nunca paga ese costo. Esta
pareja text/vision solo esta confirmada para el modelo por defecto: un
model_name de imagen distinto sin pareja conocida en _PAIRED_TEXT_MODEL
hace que embed_query_text lance EmbeddingProviderError con un mensaje
claro, en vez de intentar adivinar un nombre de modelo de texto.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from domain.rag.exceptions import EmbeddingProviderError
from domain.rag.ports import ImageEmbeddingProvider

if TYPE_CHECKING:
    from fastembed import ImageEmbedding, TextEmbedding

_DEFAULT_MODEL = "Qdrant/clip-ViT-B-32-vision"

_PAIRED_TEXT_MODEL = {
    # Unica pareja texto/vision confirmada hoy (ver docstring del
    # modulo): ambos lados de "Qdrant/clip-ViT-B-32-*", 512 dimensiones.
    "Qdrant/clip-ViT-B-32-vision": "Qdrant/clip-ViT-B-32-text",
}


class FastEmbedImageProvider(ImageEmbeddingProvider):
    def __init__(self, model_name: str = _DEFAULT_MODEL, cache_dir: Optional[str | Path] = None):
        self._model_name = model_name
        self._cache_dir = str(cache_dir) if cache_dir is not None else None
        # carga perezosa: no se descarga nada hasta el primer embed_images
        # (mismo criterio que FastEmbedEmbeddingProvider._ensure_loaded).
        self._model: Optional["ImageEmbedding"] = None
        self._dimensions: Optional[int] = None
        # carga perezosa independiente del modelo de vision de arriba --
        # ver docstring del modulo (embed_query_text).
        self._text_model: Optional["TextEmbedding"] = None

    def _ensure_loaded(self) -> "ImageEmbedding":
        if self._model is not None:
            return self._model
        try:
            from fastembed import ImageEmbedding
        except ImportError as exc:  # pragma: no cover - dependencia declarada en pyproject
            raise EmbeddingProviderError(
                "El paquete 'fastembed' no esta instalado. Agrega la dependencia "
                "declarada en pyproject.toml/requirements.txt e instala de nuevo."
            ) from exc
        try:
            self._model = ImageEmbedding(model_name=self._model_name, cache_dir=self._cache_dir)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"No se pudo cargar el modelo de embeddings de imagen {self._model_name!r}. "
                f"La primera vez requiere descargarlo de Hugging Face: revisa la "
                f"conexion a internet. Detalle original: {exc}"
            ) from exc
        return self._model

    @property
    def provider_name(self) -> str:
        return "fastembed"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            # Igual que FastEmbedEmbeddingProvider.dimensions: sin una
            # imagen real a mano en este punto, no hay forma de forzar
            # una llamada minima -- los adaptadores que necesiten
            # dimensions antes de la primera embed_images deben pasar
            # una imagen de referencia o usar una constante conocida
            # del modelo (ver README del modelo en Hugging Face).
            raise EmbeddingProviderError(
                f"Las dimensiones del modelo {self._model_name!r} todavia no se "
                f"conocen -- llama a embed_images() con al menos una imagen antes "
                f"de consultar dimensions, o usa la dimension publicada del modelo "
                f"({_DEFAULT_MODEL}: 512)."
            )
        return self._dimensions

    def embed_images(self, image_paths: list[str]) -> list[list[float]]:
        if not image_paths:
            return []
        model = self._ensure_loaded()
        try:
            vectors = [v.tolist() for v in model.embed(image_paths)]
        except Exception as exc:
            raise EmbeddingProviderError(
                f"El modelo de embeddings de imagen {self._model_name!r} fallo al "
                f"generar vectores: {exc}"
            ) from exc
        if vectors:
            self._dimensions = len(vectors[0])
        return vectors

    def _ensure_text_model_loaded(self) -> "TextEmbedding":
        if self._text_model is not None:
            return self._text_model
        paired_model = _PAIRED_TEXT_MODEL.get(self._model_name)
        if paired_model is None:
            raise EmbeddingProviderError(
                f"El modelo de imagen {self._model_name!r} no tiene un codificador "
                "de texto pareado conocido -- embed_query_text solo esta disponible "
                f"para: {', '.join(sorted(_PAIRED_TEXT_MODEL))}."
            )
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - dependencia declarada en pyproject
            raise EmbeddingProviderError(
                "El paquete 'fastembed' no esta instalado. Agrega la dependencia "
                "declarada en pyproject.toml/requirements.txt e instala de nuevo."
            ) from exc
        try:
            self._text_model = TextEmbedding(model_name=paired_model, cache_dir=self._cache_dir)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"No se pudo cargar el modelo de embeddings de texto {paired_model!r} "
                f"(pareja de {self._model_name!r}). La primera vez requiere "
                f"descargarlo de Hugging Face: revisa la conexion a internet. "
                f"Detalle original: {exc}"
            ) from exc
        return self._text_model

    def embed_query_text(self, text: str) -> list[float]:
        model = self._ensure_text_model_loaded()
        try:
            [vector] = list(model.embed([text]))
        except Exception as exc:
            raise EmbeddingProviderError(
                f"El modelo de embeddings de texto pareado con {self._model_name!r} "
                f"fallo al generar el vector de la consulta: {exc}"
            ) from exc
        return vector.tolist()
