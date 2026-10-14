"""Pruebas unitarias de contratos por defecto de los puertos del
contexto RAG (Etapa 4 / Fase 3 de multimodalidad nativa, RAG 3) -- sin
ningún adaptador real, solo el comportamiento que el propio puerto
define para quien no lo sobreescribe."""
import pytest

from domain.rag.ports import ImageEmbeddingProvider


class _MinimalImageEmbeddingProvider(ImageEmbeddingProvider):
    """Adaptador mínimo que solo implementa lo abstracto -- pensado
    para probar el comportamiento por defecto (no sobreescrito) de
    embed_query_text, mismo criterio que test_embedding_provider_embed_query_default_delegates_to_embed_texts
    en test_rag_service.py, pero para el puerto hermano de imágenes."""

    @property
    def provider_name(self) -> str:
        return "minimal"

    @property
    def model_name(self) -> str:
        return "modelo-sin-pareja-de-texto"

    @property
    def dimensions(self) -> int:
        return 4

    def embed_images(self, image_paths: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0, 0.0] for _ in image_paths]


def test_embed_query_text_default_raises_not_implemented_with_clear_message():
    provider = _MinimalImageEmbeddingProvider()
    with pytest.raises(NotImplementedError, match="modelo-sin-pareja-de-texto"):
        provider.embed_query_text("una consulta")
