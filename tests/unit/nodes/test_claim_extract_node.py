"""AgentCore Platform v1.0"""

import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.claim_extract_node import ClaimExtractNode


def _state_with_claims(base_state, claims, product_category="skincare"):
    brief = {"claims": claims, "product_category": product_category}
    return {**base_state, "validated_input": json.dumps(brief)}


class TestClaimExtractNode:
    def setup_method(self):
        self.node = ClaimExtractNode()

    def test_prefilter_hit_always_flagged_high_risk(self, base_state):
        """BL-01: keyword pre-filter runs before LLM call; hits are always risk_level high."""
        state = _state_with_claims(base_state, ["絶対に痩せる", "Improves texture"])
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        prefilter_claim = next(c for c in result["claims"] if c["text"] == "絶対に痩せる")
        assert prefilter_claim["risk_level"] == "high"
        assert prefilter_claim["category"] == "prohibited_expression"

    def test_no_claims_in_brief_returns_error(self, base_state):
        state = _state_with_claims(base_state, [])
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_empty_claims_after_parsing_returns_error(self, base_state, monkeypatch):
        """BL-02: empty claims list after parsing (post pre-filter + LLM) maps to ERROR."""
        state = _state_with_claims(base_state, ["some claim"])

        async def _empty_classify(self, claims, product_category, ctx):
            return []

        monkeypatch.setattr(
            "src.services.llm_classification_service.LLMClassificationService.classify_claims",
            _empty_classify,
        )
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_llm_failure_returns_retry(self, base_state, monkeypatch):
        """BL-03: LLM call failure maps to RETRY."""
        state = _state_with_claims(base_state, ["some claim"])

        async def _raise(self, claims, product_category, ctx):
            raise RuntimeError("LLM unavailable")

        monkeypatch.setattr(
            "src.services.llm_classification_service.LLMClassificationService.classify_claims",
            _raise,
        )
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.RETRY.value

    def test_claims_shape_is_flat_dicts(self, base_state):
        state = _state_with_claims(base_state, ["Improves skin texture"])
        result = self.node.execute(state)
        for claim in result["claims"]:
            assert set(claim.keys()) >= {"text", "category", "risk_level"}
