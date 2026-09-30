"""AgentCore Platform v1.0"""

import json

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.base import NullProvider
from framework.secrets.context import bound_secrets
from src.graph.graph import RetailVideoStoryboardAgent

VALID_BRIEF = json.dumps(
    {
        "product_name": "Glow Serum",
        "claims": ["Improves skin texture"],
        "platform": "tiktok_shop_jp",
        "duration": 30,
    }
)


@pytest.fixture
def compiled_agent():
    agent = RetailVideoStoryboardAgent()
    agent.compile()
    return agent


class TestAgentEndToEnd:
    """Full outer-graph invocation: initialize -> pre_process -> main (inner
    4-step pipeline) -> post_process -> finalize, per docs/02_design.md."""

    def test_valid_brief_produces_compliance_checked_output(self, compiled_agent):
        ctx = InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
        with bound_secrets(NullProvider()):
            result = compiled_agent.invoke(VALID_BRIEF, ctx=ctx)

        assert result["status"] == AgentStatus.SUCCESS.value
        expected_nodes = [
            "InitializeNode",
            "PreProcessNode",
            "StoryboardScriptGraphNode",
            "PostProcessNode",
            "FinalizeNode",
        ]
        assert result["node_history"] == expected_nodes

        output = result["output"]
        assert output["compliance_verdict"] in ("PASS", "NEEDS_REVISION", "FAIL")
        assert output["compliance_report"]["disclosure_inserted"] is True
        assert output["script"]["scenes"]

    def test_invalid_brief_short_circuits_before_post_process(self, compiled_agent):
        """Unsupported platform fails at pre_process; post_process is skipped
        on ERROR status (backbone routes ERROR straight to finalize)."""
        invalid_brief = json.dumps(
            {
                "product_name": "Glow Serum",
                "claims": ["Improves skin texture"],
                "platform": "unsupported_platform",
                "duration": 30,
            }
        )
        ctx = InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
        with bound_secrets(NullProvider()):
            result = compiled_agent.invoke(invalid_brief, ctx=ctx)

        assert result["status"] == AgentStatus.ERROR.value
        assert "PostProcessNode" not in result["node_history"]
