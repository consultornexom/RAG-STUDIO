"""Dobles de prueba en memoria para el contexto Ingesta."""
from __future__ import annotations

from typing import Optional

from domain.documents.entities import SourceType
from domain.ingestion.entities import Chunk, ExtractionRecord, FragmentationPolicy
from domain.ingestion.exceptions import TokenizerError, UnsupportedSourceTypeError
from domain.ingestion.ports import (
    ChunkRepository, ExtractionRepository, FragmentationPolicyRepository, TextExtractor, TokenCounter,
)


class InMemoryExtractionRepository(ExtractionRepository):
    def __init__(self):
        self._by_source: dict[str, ExtractionRecord] = {}
        self._history: list[ExtractionRecord] = []

    def save(self, record: ExtractionRecord) -> None:
        self._by_source[record.source_id] = record
        self._history.append(record)

    def get(self, project_id: str, source_id: str) -> Optional[ExtractionRecord]:
        record = self._by_source.get(source_id)
        return record if record and record.project_id == project_id else None

    def list_history(self, project_id: str, source_id: str) -> list[ExtractionRecord]:
        matches = [
            r for r in self._history if r.project_id == project_id and r.source_id == source_id
        ]
        return sorted(matches, key=lambda r: r.extracted_at, reverse=True)


class InMemoryChunkRepository(ChunkRepository):
    def __init__(self):
        self._by_source: dict[str, list[Chunk]] = {}
        # fail_replace_for_source (auditoría posterior a la Ronda 76):
        # gancho de prueba -- cuando es True, replace_for_source()
        # lanza DESPUÉS de "calcular" los chunks nuevos pero ANTES de
        # remplazar los viejos, para confirmar que un fallo a mitad de
        # camino no deja la fuente con menos chunks que antes.
        self.fail_replace_for_source = False

    def save_many(self, project_id: str, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._by_source.setdefault(chunk.source_id, []).append(chunk)

    def list_for_source(self, project_id: str, source_id: str) -> list[Chunk]:
        return list(self._by_source.get(source_id, []))

    def list_for_project(self, project_id: str) -> list[Chunk]:
        return [
            chunk for chunks in self._by_source.values() for chunk in chunks
            if chunk.project_id == project_id
        ]

    def get(self, project_id: str, chunk_id: str) -> Optional[Chunk]:
        for chunks in self._by_source.values():
            for chunk in chunks:
                if chunk.id == chunk_id and chunk.project_id == project_id:
                    return chunk
        return None

    def delete_for_source(self, project_id: str, source_id: str) -> None:
        self._by_source.pop(source_id, None)

    def replace_for_source(self, project_id: str, source_id: str, chunks: list[Chunk]) -> None:
        if self.fail_replace_for_source:
            raise RuntimeError("simulado: fallo a mitad de replace_for_source")
        self._by_source[source_id] = list(chunks)


class InMemoryFragmentationPolicyRepository(FragmentationPolicyRepository):
    def __init__(self):
        self._by_key: dict[tuple[str, str], FragmentationPolicy] = {}

    def save_policy(self, policy: FragmentationPolicy) -> None:
        self._by_key[(policy.project_id, policy.document_type_code)] = policy

    def get_policy(self, project_id: str, document_type_code: str) -> Optional[FragmentationPolicy]:
        return self._by_key.get((project_id, document_type_code))

    def list_policies(self, project_id: str) -> list[FragmentationPolicy]:
        return [p for (pid, _), p in self._by_key.items() if pid == project_id]


class FakeTextExtractor(TextExtractor):
    """Extractor de prueba: devuelve texto "enlatado" por ubicación, o
    un texto genérico si no se configuró nada para esa ubicación."""

    def __init__(
        self, canned: Optional[dict] = None, supported_types: Optional[set] = None,
        raise_os_error: Optional[OSError] = None, canned_structured: Optional[dict] = None,
    ):
        self._canned = canned or {}
        self._supported_types = supported_types or {
            SourceType.TXT, SourceType.MARKDOWN, SourceType.DOCX, SourceType.PDF,
        }
        self._raise_os_error = raise_os_error
        # Pista B.2 del ADR-003: bloques estructurados "enlatados" por
        # ubicación -- mismo criterio que `canned`, pero para
        # extract_structured_blocks() en vez de extract().
        self._canned_structured = canned_structured or {}

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._supported_types

    def extract(self, location: str, source_type: SourceType) -> tuple[str, str, list[int], list[str]]:
        if not self.supports(source_type):
            raise UnsupportedSourceTypeError(source_type.value)
        if self._raise_os_error is not None:
            raise self._raise_os_error
        if location in self._canned:
            return self._canned[location]
        return (f"contenido de prueba para {location}", "fake", [], [])

    def extract_structured_blocks(self, location: str, source_type: SourceType) -> dict[str, dict]:
        return self._canned_structured.get(location, {})


class FakeTokenCounter(TokenCounter):
    """Doble de prueba de TokenCounter (ítem 7 de la evaluación de
    madurez post-8-etapas): `tokens_per_word` distinto de 1 para que
    las pruebas puedan distinguir con certeza que se usó ESTE contador
    y no la aproximación por palabras (word_count) de siempre."""

    def __init__(self, tokens_per_word: int = 2):
        self._tokens_per_word = tokens_per_word
        self.calls: list[str] = []

    def count_tokens(self, text: str) -> int:
        self.calls.append(text)
        return len(text.split()) * self._tokens_per_word


class FailingTokenCounter(TokenCounter):
    """Simula un tokenizador real no disponible en este momento (sin
    conexión a internet para la descarga inicial, ver
    infrastructure.tokenization.tiktoken_counter) -- para probar que
    FragmentSource cae de vuelta a word_count sin tumbar la
    fragmentación."""

    def count_tokens(self, text: str) -> int:
        raise TokenizerError("simulado: sin conexión para descargar la codificación")
