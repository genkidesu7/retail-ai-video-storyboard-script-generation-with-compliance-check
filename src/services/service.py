"""AgentCore Platform v1.0"""

# Service layer: vector KB search against the 景品表示法/消費者庁 rules corpus.
# Must NOT contain business logic, routing, or credentials.
# Nodes call this; this calls shared/services/ for the underlying vector store.

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class ComplianceKBTransientError(Exception):
    """Raised when the compliance KB is temporarily unreachable (maps to RETRY)."""


class ComplianceKBPermanentError(Exception):
    """Raised for permanent/unexpected KB failures (maps to ERROR)."""


class ComplianceKBService:
    """Vector KB search against the 景品表示法/消費者庁 rules corpus.

    Usage from a node::

        service = ComplianceKBService()
        hits = await service.search(scene_text, credential_handle)
    """

    async def search(
        self,
        query: str,
        credential_handle: str,
    ) -> list[dict[str, Any]]:
        """Search the compliance KB for rule citations matching query text.

        Args:
            query: Scene dialogue or on-screen text to check.
            credential_handle: Opaque handle from InvocationContext.secrets.require().
                Never log or store this value.

        Returns:
            List of rule citation dicts, e.g.
            [{"rule_id": str, "rule_citation": str, "matched_text": str, "score": float}].

        Raises:
            ComplianceKBTransientError: KB unreachable — caller should map to RETRY.
            ComplianceKBPermanentError: unexpected/permanent failure — maps to ERROR.
        """
        if not credential_handle:
            raise ComplianceKBPermanentError(
                "ComplianceKBService.search: credential_handle is empty — " "check InvocationContext configuration"
            )
        return await self._call_external(query, credential_handle)

    async def _call_external(
        self,
        query: str,
        credential_handle: str,
    ) -> list[dict[str, Any]]:
        # No vector-store backend is provisioned for this template, and the deploy contract
        # keeps every non-LLM service on mock data even when mock mode is off (only the LLM
        # call is ever real). The rules corpus is therefore always served by the stub.
        from src.services.mock_data import stub_kb_search

        return await stub_kb_search(query, credential_handle)
