"""AgentCore Platform v1.0"""

import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.pre_process_node import PreProcessNode

VALID_BRIEF = {
    "product_name": "Glow Serum",
    "claims": ["Improves skin texture"],
    "platform": "tiktok_shop_jp",
    "duration": 30,
}


class TestPreProcessNode:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_valid_brief_produces_validated_input(self, base_state):
        state = {**base_state, "user_input": json.dumps(VALID_BRIEF)}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["validated_input"]["product_name"] == "Glow Serum"
        assert result["platform_config"]["aspect_ratio"] == "9:16"

    def test_missing_required_field_returns_error(self, base_state):
        brief = {k: v for k, v in VALID_BRIEF.items() if k != "duration"}
        state = {**base_state, "user_input": json.dumps(brief)}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]

    def test_unsupported_platform_returns_error(self, base_state):
        """BL-10: unsupported platform maps to ERROR with error_log entry."""
        brief = {**VALID_BRIEF, "platform": "unknown_platform"}
        state = {**base_state, "user_input": json.dumps(brief)}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert "unsupported platform" in result["error_log"][0].lower()

    def test_empty_user_input_returns_error(self, base_state):
        state = {**base_state, "user_input": ""}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_invalid_json_returns_error(self, base_state):
        state = {**base_state, "user_input": "not json"}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
