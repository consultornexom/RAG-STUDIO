"""Caso de uso: crear o actualizar (upsert) la FragmentationPolicy de
un document_type_code dentro de un proyecto."""
from __future__ import annotations

from domain.ingestion.entities import FragmentationPolicy, FragmentationStrategy
from domain.ingestion.ports import FragmentationPolicyRepository


class SetFragmentationPolicy:
    def __init__(self, repository: FragmentationPolicyRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        document_type_code: str,
        strategy: FragmentationStrategy = FragmentationStrategy.POR_TAMANIO,
        target_tokens: int = 500,
        overlap_tokens: int = 60,
        min_tokens: int = 80,
    ) -> FragmentationPolicy:
        existing = self._repository.get_policy(project_id, document_type_code)
        # Se construye con dos ramas explícitas (en vez de **identity con
        # un dict heterogéneo) para que el tipo de cada campo quede
        # claro y verificable: mismo comportamiento, sin perder
        # precisión de tipos.
        if existing is not None:
            policy = FragmentationPolicy(
                id=existing.id, created_at=existing.created_at,
                project_id=project_id, document_type_code=document_type_code, strategy=strategy,
                target_tokens=target_tokens, overlap_tokens=overlap_tokens, min_tokens=min_tokens,
            )
        else:
            policy = FragmentationPolicy(
                project_id=project_id, document_type_code=document_type_code, strategy=strategy,
                target_tokens=target_tokens, overlap_tokens=overlap_tokens, min_tokens=min_tokens,
            )
        self._repository.save_policy(policy)
        return policy
