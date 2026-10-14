"""Adaptador EmbeddingProvider sobre el paquete `fastembed` (modelo
ONNX local, sin API keys ni costo por uso). Implementa el puerto
domain.rag.ports.EmbeddingProvider.

Se usa el paquete `fastembed` directamente -- no el extra
`qdrant-client[fastembed]` -- para que EmbeddingProvider y VectorStore
sigan siendo dos puertos independientes y sustituibles por separado
(ADR-001, seccion 4): domain/application nunca deberian tener que
saber que ambos vienen del mismo proveedor.

Modelo por defecto: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
(384 dimensiones, ~220 MB, multilingue ~50 idiomas). Se eligio sobre el
modelo de ejemplo de la documentacion de fastembed/qdrant-client
(BAAI/bge-small-en-v1.5, solo ingles) porque las fuentes reales de
RAG STUDIO son en espanol (reglamentos, manuales; ver INVESTIGACION.odt
y el piloto UDL) -- un modelo mono-ingles degradaria la busqueda
semantica sobre ese contenido.

Limitacion importante (ver README): el modelo se descarga de Hugging
Face la primera vez que se usa. Sin conexion a internet en ese primer
uso, embed_texts lanza EmbeddingProviderError -- no hay modo
completamente offline "desde cero" todavia. Una vez descargado queda
en cache_dir (por defecto, InstallationPaths.models_dir(): un directorio
compartido por todos los proyectos de la instalacion, no uno por
proyecto, para no repetir la descarga).

Modelos simetricos vs. asimetricos (ver README, seccion "Proximos
pasos" y bitacora 2026-07-25/2026-07-26): el modelo por defecto es
simetrico -- compara frases de estilo parecido entre si, sin distinguir
"pregunta" de "pasaje". Algunos modelos (familia intfloat/e5, entre
otros) se entrenan de forma ASIMETRICA: esperan un prefijo distinto en
cada lado ("query: " para la consulta, "passage: " para el texto que
se indexa) para dar su mejor resultado en tareas de "pregunta busca
pasaje". Este adaptador soporta ambos casos via query_prefix/
passage_prefix (vacios por defecto = comportamiento simetrico, sin
cambios respecto a versiones anteriores); ver
make_multilingual_e5_large_provider() para una fabrica lista para el
unico modelo asimetrico multilingue que fastembed trae empaquetado.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from domain.rag.exceptions import EmbeddingProviderError
from domain.rag.ports import EmbeddingProvider

if TYPE_CHECKING:
    from fastembed import TextEmbedding

_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Unico modelo multilingue asimetrico ("query busca passage") que trae
# fastembed empaquetado (ver TextEmbedding.list_supported_models() --
# no incluye bge-m3 ni multilingual-e5-base, solo la version "large").
# Prefijos segun la tarjeta del modelo en Hugging Face
# (intfloat/multilingual-e5-large): sin ellos, el modelo no aplica el
# entrenamiento asimetrico y el resultado puede ser peor que el modelo
# simetrico por defecto, no mejor.
_E5_LARGE_MODEL = "intfloat/multilingual-e5-large"
_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


class FastEmbedEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self, model_name: str = _DEFAULT_MODEL, cache_dir: Optional[str | Path] = None,
        query_prefix: str = "", passage_prefix: str = "",
    ):
        self._model_name = model_name
        self._cache_dir = str(cache_dir) if cache_dir is not None else None
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix
        # carga perezosa: no se descarga nada hasta el primer embed_texts/embed_query
        self._model: Optional["TextEmbedding"] = None
        self._dimensions: Optional[int] = None

    def _ensure_loaded(self) -> "TextEmbedding":
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - dependencia declarada en pyproject
            raise EmbeddingProviderError(
                "El paquete 'fastembed' no esta instalado. Agrega la dependencia "
                "declarada en pyproject.toml/requirements.txt e instala de nuevo."
            ) from exc
        try:
            self._model = TextEmbedding(model_name=self._model_name, cache_dir=self._cache_dir)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"No se pudo cargar el modelo de embeddings {self._model_name!r}. "
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
            # embed_texts calcula y guarda self._dimensions la primera vez;
            # forzamos una llamada minima si todavia no se ha usado el modelo.
            self.embed_texts([""])
        return self._dimensions  # type: ignore[return-value]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Lado "pasaje": aplica passage_prefix (vacio en el modelo
        simetrico por defecto)."""
        if not texts:
            return []
        prefixed = [f"{self._passage_prefix}{t}" for t in texts] if self._passage_prefix else texts
        return self._embed_raw(prefixed)

    def embed_query(self, text: str) -> list[float]:
        """Lado "consulta": aplica query_prefix (vacio en el modelo
        simetrico por defecto, igual que embed_texts -- ver
        domain.rag.ports.EmbeddingProvider.embed_query)."""
        prefixed = f"{self._query_prefix}{text}" if self._query_prefix else text
        [vector] = self._embed_raw([prefixed])
        return vector

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_loaded()
        try:
            vectors = [v.tolist() for v in model.embed(texts)]
        except Exception as exc:
            raise EmbeddingProviderError(
                f"El modelo de embeddings {self._model_name!r} fallo al generar "
                f"vectores: {exc}"
            ) from exc
        if vectors:
            self._dimensions = len(vectors[0])
        return vectors


def make_multilingual_e5_large_provider(cache_dir: Optional[str | Path] = None) -> FastEmbedEmbeddingProvider:
    """Fabrica para el experimento de modelo asimetrico (ver README,
    bitacora): intfloat/multilingual-e5-large, 1024 dimensiones, con
    los prefijos query:/passage: que pide la tarjeta del modelo.
    Mucho mas pesado que el modelo simetrico por defecto (~2 GB vs.
    ~220 MB) -- por eso no es el default, solo una opcion explicita."""
    return FastEmbedEmbeddingProvider(
        model_name=_E5_LARGE_MODEL, cache_dir=cache_dir,
        query_prefix=_E5_QUERY_PREFIX, passage_prefix=_E5_PASSAGE_PREFIX,
    )


# Perfiles con nombre corto (ver README, bitacora 2026-07-26: el
# experimento real confirmo que el modelo asimetrico mejora busquedas
# en lenguaje natural contra contenido tipo lista, a cambio de 10x mas
# peso/tiempo de descarga -- el usuario decidio NO cambiar el default,
# sino dejarlo como opcion explicita para quien lo necesite). Pensado
# para configurarse por variable de entorno (RAGSTUDIO_EMBEDDING_PROFILE,
# ver app.configuration) o por parametro explicito en bootstrap()/
# start(), sin que nadie que no lo pida se entere del cambio.
PERFIL_SIMETRICO = "simetrico"
PERFIL_ASIMETRICO_E5_LARGE = "asimetrico_e5_large"
_PERFILES_VALIDOS = (PERFIL_SIMETRICO, PERFIL_ASIMETRICO_E5_LARGE)

# Alias publico de _PERFILES_VALIDOS: el comparador de modelos (A vs B,
# ui/ingestion/panel.py) necesita listar los perfiles disponibles para
# llenar los selectores, sin importar un nombre "privado" desde otra capa.
AVAILABLE_EMBEDDING_PROFILES = _PERFILES_VALIDOS

# Ronda 92: modelo que usa cada perfil -- permite que el runtime derive el
# perfil a partir del modelo con que se construyó el índice de una
# instantánea (index_info.embedding_model) y rechace al arrancar un perfil
# que no corresponda, en vez de consultar el índice con otro modelo.
EMBEDDING_MODEL_BY_PROFILE = {
    PERFIL_SIMETRICO: _DEFAULT_MODEL,
    PERFIL_ASIMETRICO_E5_LARGE: _E5_LARGE_MODEL,
}


def make_provider_for_profile(
    profile: str = PERFIL_SIMETRICO, cache_dir: Optional[str | Path] = None,
) -> FastEmbedEmbeddingProvider:
    """Resuelve un EmbeddingProvider a partir de un nombre de perfil
    corto, sin exponer nombres de modelo ni prefijos crudos a quien
    solo quiere elegir entre "el de siempre" (ligero, simetrico) y "el
    pesado que entiende mejor preguntas en lenguaje natural" (asimetrico).
    Lanza ValueError con perfiles validos en el mensaje si el nombre no
    se reconoce -- mejor fallar claro al arrancar que silenciosamente
    usar el default."""
    if profile == PERFIL_SIMETRICO:
        return FastEmbedEmbeddingProvider(cache_dir=cache_dir)
    if profile == PERFIL_ASIMETRICO_E5_LARGE:
        return make_multilingual_e5_large_provider(cache_dir=cache_dir)
    raise ValueError(
        f"Perfil de modelo de embeddings desconocido: {profile!r}. "
        f"Perfiles disponibles: {', '.join(repr(p) for p in _PERFILES_VALIDOS)}."
    )
