from __future__ import annotations

from typing import Optional

from domain.conversational.entities import RuleActionType
from domain.quality.entities import TestCase, TestCategory, TestSeverity
from domain.quality.exceptions import DuplicateTestCaseCodeError
from domain.quality.ports import TestCaseRepository


class CreateTestCase:
    def __init__(self, repository: TestCaseRepository):
        self._repository = repository

    def execute(
        self, project_id: str, code: str, category: TestCategory, query_text: str,
        provided_variables: Optional[dict[str, str]] = None, source_id: Optional[str] = None,
        expected_intent: Optional[str] = None, expected_missing_variable: Optional[str] = None,
        expected_action: Optional[RuleActionType] = None, forbidden_action: Optional[RuleActionType] = None,
        expected_channeling: bool = False, expected_source_id: Optional[str] = None,
        severity: TestSeverity = TestSeverity.MEDIA,
    ) -> TestCase:
        code = code.strip()
        if any(existing.code == code for existing in self._repository.list_for_project(project_id)):
            raise DuplicateTestCaseCodeError(code)
        test_case = TestCase(
            project_id=project_id, code=code, category=category, query_text=query_text,
            provided_variables=dict(provided_variables or {}), source_id=source_id,
            expected_intent=expected_intent, expected_missing_variable=expected_missing_variable,
            expected_action=expected_action, forbidden_action=forbidden_action,
            expected_channeling=expected_channeling, expected_source_id=expected_source_id,
            severity=severity,
        )
        self._repository.save(test_case)
        return test_case
