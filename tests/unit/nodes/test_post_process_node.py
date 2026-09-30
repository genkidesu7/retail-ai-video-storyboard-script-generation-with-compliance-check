"""AgentCore Platform v1.0"""

from framework.schemas.agent_status import AgentStatus
from src.nodes.post_process_node import PostProcessNode


class TestPostProcessNode:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_passes_through_upstream_error_unchanged(self, base_state):
        state = {**base_state, "status": AgentStatus.ERROR.value}
        result = self.node.execute(state)
        assert result == {"status": AgentStatus.ERROR.value}

    def test_success_surfaces_compliance_verdict_at_top_level(self, base_state):
        state = {
            **base_state,
            "status": AgentStatus.SUCCESS.value,
            "result": {"scenes": []},
            "compliance_report": {"verdict": "PASS", "findings": []},
            "compliance_verdict": "PASS",
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["formatted_output"]["compliance_verdict"] == "PASS"
        assert result["formatted_output"]["compliance_report"]["verdict"] == "PASS"
