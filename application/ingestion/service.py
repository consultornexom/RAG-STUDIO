"""Fachada de application para el contexto Ingesta."""
from __future__ import annotations

from typing import Callable, Optional

from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk, ExtractionRecord, FragmentationPolicy, FragmentationStrategy
from domain.ingestion.ports import (
    ChunkRepository, ExtractionRepository, FragmentationPolicyRepository, TextExtractor, TokenCounter,
)
from domain.metadata.ports import MetadataSchemaRepository, SourceMetadataRepository

from .commands.extract_source_text import ExtractSourceText
from .commands.fragment_source import FragmentSource
from .commands.set_fragmentation_policy import SetFragmentationPolicy
from .queries.get_extraction_record import GetExtractionRecord
from .queries.list_chunks import ListChunks
from .queries.list_extraction_history import ListExtractionHistory
from .queries.list_fragmentation_policies import ListFragmentationPolicies


class IngestionService:
    def __init__(
        self,
        source_repository: SourceRepository,
        extractor: TextExtractor,
        extraction_repository: ExtractionRepository,
        policy_repository: FragmentationPolicyRepository,
        chunk_repository: ChunkRepository,
        schema_repository: MetadataSchemaRepository,
        source_metadata_repository: SourceMetadataRepository,
        token_counter: Optional[TokenCounter] = None,
    ):
        self._extract = ExtractSourceText(source_repository, extractor, extraction_repository)
        self._fragment = FragmentSource(
            extraction_repository, policy_repository, chunk_repository,
            schema_repository, source_metadata_repository, token_counter=token_counter,
        )
        self._set_policy = SetFragmentationPolicy(policy_repository)
        self._get_extraction = GetExtractionRecord(extraction_repository)
        self._list_extraction_history = ListExtractionHistory(extraction_repository)
        self._list_chunks = ListChunks(chunk_repository)
        self._list_policies = ListFragmentationPolicies(policy_repository)

    def extract_source_text(
        self, project_id: str, source_id: str,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> Optional[ExtractionRecord]:
        return self._extract.execute(project_id, source_id, is_cancelled=is_cancelled)

    def fragment_source(
        self, project_id: str, source_id: str, schema_id: Optional[str] = None,
        document_type_code: str = "default",
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> Optional[list[Chunk]]:
        return self._fragment.execute(
            project_id, source_id, schema_id=schema_id, document_type_code=document_type_code,
            is_cancelled=is_cancelled,
        )

    def set_fragmentation_policy(
        self, project_id: str, document_type_code: str,
        strategy: FragmentationStrategy = FragmentationStrategy.POR_TAMANIO, **kwargs,
    ) -> FragmentationPolicy:
        return self._set_policy.execute(project_id, document_type_code, strategy=strategy, **kwargs)

    def get_extraction_record(self, project_id: str, source_id: str) -> Optional[ExtractionRecord]:
        return self._get_extraction.execute(project_id, source_id)

    def list_extraction_history(self, project_id: str, source_id: str) -> list[ExtractionRecord]:
        return self._list_extraction_history.execute(project_id, source_id)

    def list_chunks(self, project_id: str, source_id: str) -> list[Chunk]:
        return self._list_chunks.execute(project_id, source_id)

    def list_fragmentation_policies(self, project_id: str) -> list[FragmentationPolicy]:
        return self._list_policies.execute(project_id)
