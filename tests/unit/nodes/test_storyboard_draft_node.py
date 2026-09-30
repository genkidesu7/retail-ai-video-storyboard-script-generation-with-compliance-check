"""AgentCore Platform v1.0"""

import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.storyboard_draft_node import StoryboardDraftNode


def _state(base_state, claims, platform_config, duration=30):
    brief = {"duration": duration, "platform_config": platform_config}
    return {
        **base_state,
        "validated_input": json.dumps(brief),
        "claims": claims,
    }


CLAIMS = [{"text": "Improves texture", "category": "quality_claim", "risk_level": "medium"}]


class TestStoryboardDraftNode:
    def setup_method(self):
        self.node = StoryboardDraftNode()

    def test_no_claims_returns_error(self, base_state):
        state = _state(base_state, [], {"max_duration_sec": 60})
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_duration_exceeding_platform_max_returns_error(self, base_state, monkeypatch):
        """BL-04: generated total duration exceeding platform max maps to ERROR, no silent truncation."""

        async def _oversized(self, claims, brief, platform_config, ctx):
            return [{"scene_no": 1, "visual_beat": "x", "duration_sec": 999, "claim_refs": ["Improves texture"]}]

        monkeypatch.setattr(
            "src.services.llm_classification_service.LLMClassificationService.generate_storyboard",
            _oversized,
        )
        state = _state(base_state, CLAIMS, {"max_duration_sec": 60})
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert "exceeds platform max" in result["error_log"][0]

    def test_llm_failure_returns_retry(self, base_state, monkeypatch):
        async def _raise(self, claims, brief, platform_config, ctx):
            raise RuntimeError("LLM timeout")

        monkeypatch.setattr(
            "src.services.llm_classification_service.LLMClassificationService.generate_storyboard",
            _raise,
        )
        state = _state(base_state, CLAIMS, {"max_duration_sec": 60})
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.RETRY.value

    def test_chunking_triggered_for_many_claims(self, base_state):
        """BL-05: chunking strategy (one scene per claim) applies for long-duration/many-claim briefs."""
        many_claims = [
            {"text": f"claim {i}", "category": "quality_claim", "risk_level": "low"} for i in range(5)
        ]
        state = _state(base_state, many_claims, {"max_duration_sec": 90}, duration=90)
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["storyboard"]) == len(many_claims)
        total_duration = sum(s["duration_sec"] for s in result["storyboard"])
        assert total_duration <= 90

    def test_success_populates_storyboard_shape(self, base_state):
        state = _state(base_state, CLAIMS, {"max_duration_sec": 60})
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        scene = result["storyboard"][0]
        assert set(scene.keys()) >= {"scene_no", "visual_beat", "duration_sec", "claim_refs"}
