"""Adaptador TokenCounter sobre `tiktoken` (tokenizador BPE real, el
mismo usado por los modelos GPT) -- ítem 7 de la evaluación de madurez
post-8-etapas: sustituye la aproximación por conteo de palabras
(domain.ingestion.splitting.word_count) por un conteo de tokens real
en el diseñador de fragmentación. Implementa
domain.ingestion.ports.TokenCounter.

Se eligió `tiktoken` (en vez de acoplarse al tokenizador interno de
`fastembed`, no expuesto como API pública estable) por ser una
dependencia liviana e independiente del modelo de embeddings elegido:
"tokens BPE reales" es un proxy razonable de tamaño de fragmento sin
importar qué proveedor de embeddings esté configurado.

Limitación importante (mismo patrón que FastEmbedEmbeddingProvider,
ver README): la codificación (~2 MB) se descarga la primera vez que se
usa, desde infraestructura pública de OpenAI. Sin conexión a internet
en ese primer uso, count_tokens lanza TokenizerError -- FragmentSource
la captura y usa `word_count` como respaldo para esa corrida (ver
FragmentSource._resolve_count_tokens), sin abortar la fragmentación.
Una vez descargada, tiktoken la deja en su propio caché local (o en
TIKTOKEN_CACHE_DIR si esa variable de entorno está configurada) y no
vuelve a necesitar red.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from domain.ingestion.exceptions import TokenizerError
from domain.ingestion.ports import TokenCounter

if TYPE_CHECKING:
    import tiktoken

_DEFAULT_ENCODING = "cl100k_base"


class TiktokenCounter(TokenCounter):
    def __init__(self, encoding_name: str = _DEFAULT_ENCODING):
        self._encoding_name = encoding_name
        # carga perezosa: no se descarga nada hasta el primer count_tokens
        self._encoding: Optional["tiktoken.Encoding"] = None

    def _ensure_loaded(self) -> "tiktoken.Encoding":
        if self._encoding is not None:
            return self._encoding
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover - dependencia declarada en pyproject
            raise TokenizerError(
                "El paquete 'tiktoken' no está instalado. Agrega la dependencia declarada "
                "en pyproject.toml e instala de nuevo."
            ) from exc
        try:
            self._encoding = tiktoken.get_encoding(self._encoding_name)
        except Exception as exc:
            raise TokenizerError(
                f"No se pudo cargar el tokenizador {self._encoding_name!r}. La primera vez "
                f"requiere descargar su codificación de internet: revisa la conexión. "
                f"Detalle original: {exc}"
            ) from exc
        return self._encoding

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        encoding = self._ensure_loaded()
        return len(encoding.encode(text))
