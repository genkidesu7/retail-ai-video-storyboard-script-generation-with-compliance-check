"""AgentCore Platform v1.0"""

import json

from framework.schemas.agent_status import AgentStatus
from src.graph.graph import StoryboardScriptGraphNode


class TestStoryboardScriptGraphNodeExtractInput:
    def setup_method(self):
        self.node = StoryboardScriptGraphNode()

    def test_extract_input_bundles_brief_and_platform_config(self):
        state = {
            "validated_input": {"product_name": "Glow Serum", "claims": ["x"]},
            "platform_config": {"aspect_ratio": "9:16", "max_duration_sec": 60},
        }
        payload = json.loads(self.node.extract_input(state))
        assert payload["product_name"] == "Glow Serum"
        assert payload["platform_config"]["max_duration_sec"] == 60

    def test_extract_input_falls_back_to_user_input(self):
        state = {"user_input": "raw"}
        # validated_input missing -> falls back to user_input, which is not a dict,
        # so brief becomes {} but platform_config key is still merged in.
        payload = json.loads(self.node.extract_input(state))
        assert "platform_config" in payload


class TestStoryboardScriptGraphNodeMergeOutput:
    def setup_method(self):
        self.node = StoryboardScriptGraphNode()

    def test_merge_output_maps_inner_fields_to_outer_state(self):
        sub_result = {
            "output": {"scenes": []},
            "compliance_report": {"verdict": "PASS"},
            "compliance_verdict": "PASS",
            "status": AgentStatus.SUCCESS.value,
        }
        merged = self.node.merge_output({}, sub_result)
        assert merged["result"] == {"scenes": []}
        assert merged["compliance_verdict"] == "PASS"
        assert merged["status"] == AgentStatus.SUCCESS.value


class TestStoryboardScriptGraphNodeErrorStrategy:
    """BL-11: error_strategy=propagate — inner SubgraphError surfaces as outer ERROR via __call__()."""

    def test_error_strategy_is_propagate(self):
        assert StoryboardScriptGraphNode.error_strategy == "propagate"

    def test_subgraph_error_surfaces_as_outer_error(self, base_state, monkeypatch):
        node = StoryboardScriptGraphNode()

        class _FailingSubgraph:
            name = "storyboard_script_workflow"

            def invoke(self, user_input, session_id, ctx):
                raise RuntimeError("inner pipeline failed")

        monkeypatch.setattr(node, "get_subgraph", lambda: _FailingSubgraph())
        state = {
            **base_state,
            "validated_input": {"product_name": "x", "claims": ["y"]},
            "platform_config": {},
            "caller_trust_level": node.required_trust_level.value,
        }
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
