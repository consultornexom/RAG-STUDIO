"""Decorador `EmbeddingProvider` que cachea en memoria el lado
CONSULTA de cualquier proveedor de embeddings real (Ronda 19, ver
Validacion_observaciones_RAG_STUDIO.md, recomendación #2 de la
evaluación de grado profesional -- Ronda 18).

Por qué solo `embed_query` y no `embed_texts`: el lado "pasaje/
documento" (`embed_texts`, usado por `IndexSource` para embeber cada
Chunk una sola vez al indexar) prácticamente nunca repite el mismo
texto -- cachearlo no ahorraría nada real y arriesgaría servir un
vector obsoleto si el mismo texto se reindexara con otro modelo. El
lado "consulta" (`embed_query`, usado por `SemanticSearch`/
`HybridSearch` y por el emparejamiento semántico de intención) sí se
repite de verdad en un runtime con muchos visitantes reales -- preguntas
frecuentes, variaciones de la misma consulta, o el mismo visitante
reformulando -- y es exactamente el punto que el consultor señaló como
de "impacto directo y medible en latencia bajo carga real" al evaluar
qué actualizaciones valían la pena para un despliegue profesional.

Por qué en `infrastructure/` y no en `application/`: es un detalle de
implementación de UN proveedor concreto (cualquiera), no una decisión
de negocio -- ADR-001, sección 4: domain/application solo conocen el
puerto `EmbeddingProvider`, nunca si hay o no un caché detrás. Se
inyecta envolviendo la construcción real (ver
`interfaces/api/runtime_context.py::_build`), sin tocar ningún llamador.

Ámbito del caché: por INSTANCIA de `CachingEmbeddingProvider`, no
global ni por proceso -- en el runtime de producción, cada instantánea
publicada (`project_id:version`) construye su propio proveedor (ver
`RuntimeContext._build`), así que el caché se descarta solo junto con
esa instantánea cuando se publica una nueva versión (mismo ciclo de
vida que ya tiene el resto de `LoadedSnapshot`, ver
`RuntimeContext._get_or_build`) -- nunca sirve un resultado calculado
contra un índice o un modelo que ya no está vigente."""
from __future__ import annotations

from collections import OrderedDict

from domain.rag.ports import EmbeddingProvider

_DEFAULT_MAX_ENTRIES = 512
"""Tope de consultas distintas recordadas a la vez -- un vector típico
de este proyecto (384 dimensiones, float) pesa unos pocos KB; incluso
el máximo de entradas se queda muy por debajo de lo que costaría
mantener cargado el propio modelo de embeddings en RAM."""


class CachingEmbeddingProvider(EmbeddingProvider):
    """Envuelve cualquier `EmbeddingProvider` real y cachea el
    resultado de `embed_query` con una política LRU simple (least
    recently used) -- `embed_texts` y las propiedades se delegan tal
    cual, sin ningún cambio de comportamiento."""

    def __init__(self, wrapped: EmbeddingProvider, max_entries: int = _DEFAULT_MAX_ENTRIES):
        self._wrapped = wrapped
        self._max_entries = max_entries
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        # hits/misses (no son parte del puerto EmbeddingProvider):
        # expuestos para que quien construya el runtime pueda registrar
        # en el log, si algún día conviene, qué tan efectivo está siendo
        # el caché para un proyecto real -- y para que las pruebas
        # puedan verificar el comportamiento sin depender de mockear
        # el proveedor envuelto.
        self.hits = 0
        self.misses = 0

    @property
    def provider_name(self) -> str:
        return self._wrapped.provider_name

    @property
    def model_name(self) -> str:
        return self._wrapped.model_name

    @property
    def dimensions(self) -> int:
        return self._wrapped.dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._wrapped.embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        # .strip() (no .lower()): normaliza espacios accidentales al
        # inicio/fin (p. ej. un textarea que deja un salto de línea),
        # que de otro modo fallarían el caché por una diferencia
        # invisible para quien pregunta -- pero no toca mayúsculas ni
        # acentos, para no arriesgar que dos consultas realmente
        # distintas para el modelo (p. ej. un acrónimo en mayúsculas
        # con significado propio) compartan la misma entrada sin que
        # nada en este módulo pueda saber si eso es seguro para el
        # modelo vigente.
        key = text.strip()
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            self.hits += 1
            return cached
        self.misses += 1
        vector = self._wrapped.embed_query(text)
        self._cache[key] = vector
        if len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)  # descarta la entrada usada hace más tiempo
        return vector

    def cache_info(self) -> dict[str, int]:
        """Ronda 19: para diagnóstico/pruebas -- cuántas entradas hay
        cacheadas ahora mismo, y cuántos aciertos/fallos ha habido
        desde que se construyó este proveedor."""
        return {"entries": len(self._cache), "hits": self.hits, "misses": self.misses}
