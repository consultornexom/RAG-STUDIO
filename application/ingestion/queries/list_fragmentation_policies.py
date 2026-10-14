from __future__ import annotations

from domain.ingestion.entities import FragmentationPolicy
from domain.ingestion.ports import FragmentationPolicyRepository


class ListFragmentationPolicies:
    def __init__(self, repository: FragmentationPolicyRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[FragmentationPolicy]:
        return self._repository.list_policies(project_id)
