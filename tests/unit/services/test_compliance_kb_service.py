"""AgentCore Platform v1.0"""

import pytest

from src.services.service import ComplianceKBPermanentError, ComplianceKBService


class TestComplianceKBService:
    @pytest.mark.asyncio
    async def test_search_returns_citations_in_mock_mode(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        service = ComplianceKBService()
        hits = await service.search("some scene text", "mock-handle")
        assert hits
        assert "rule_citation" in hits[0]

    @pytest.mark.asyncio
    async def test_empty_credential_handle_raises_permanent_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        service = ComplianceKBService()
        with pytest.raises(ComplianceKBPermanentError):
            await service.search("some scene text", "")

    @pytest.mark.asyncio
    async def test_non_mock_mode_still_serves_mock_corpus(self, monkeypatch):
        """Only the LLM is real outside mock mode; the KB has no provisioned backend."""
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        service = ComplianceKBService()
        hits = await service.search("some scene text", "handle")
        assert hits and hits[0]["rule_citation"]
