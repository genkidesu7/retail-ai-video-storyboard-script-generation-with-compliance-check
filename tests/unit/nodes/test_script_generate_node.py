"""AgentCore Platform v1.0"""

from framework.schemas.agent_status import AgentStatus
from src.nodes.script_generate_node import ScriptGenerateNode

STORYBOARD = [
    {"scene_no": 1, "visual_beat": "Scene 1", "duration_sec": 15, "claim_refs": ["Improves texture"]},
]
CLAIMS = [{"text": "Improves texture", "category": "quality_claim", "risk_level": "medium"}]


class TestScriptGenerateNode:
    def setup_method(self):
        self.node = ScriptGenerateNode()

    def test_no_storyboard_returns_error(self, base_state):
        state = {**base_state, "storyboard": [], "claims": CLAIMS}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_unmapped_claim_returns_error(self, base_state):
        """BL-06: a claim not referenced by any scene's claim_refs maps to ERROR."""
        claims = CLAIMS + [{"text": "Dermatologist tested", "category": "quality_claim", "risk_level": "low"}]
        state = {**base_state, "storyboard": STORYBOARD, "claims": claims}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert "Dermatologist tested" in result["error_log"][0]

    def test_llm_failure_returns_retry(self, base_state, monkeypatch):
        async def _raise(self, storyboard, claims, ctx):
            raise RuntimeError("LLM error")

        monkeypatch.setattr(
            "src.services.llm_classification_service.LLMClassificationService.generate_script",
            _raise,
        )
        state = {**base_state, "storyboard": STORYBOARD, "claims": CLAIMS}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.RETRY.value

    def test_success_maps_every_claim_to_a_scene(self, base_state):
        state = {**base_state, "storyboard": STORYBOARD, "claims": CLAIMS}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        all_refs = {ref for scene in result["script"]["scenes"] for ref in scene["claim_refs"]}
        assert all(c["text"] in all_refs for c in CLAIMS)
