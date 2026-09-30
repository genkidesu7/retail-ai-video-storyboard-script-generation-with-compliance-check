"""AgentCore Platform v1.0"""

import json
from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.graph.base_graph import BaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State


class StoryboardScriptGraphNode(GraphNode):
    """Outer `main` slot — wraps the inner 4-step compliance pipeline.

    error_strategy="propagate": any inner RETRY/ERROR surfaces as SubgraphError,
    which the outer main node reports as ERROR upstream — no partial or
    unvalidated scripts are ever surfaced. No HITL interrupt wired (out of
    scope per design).
    """

    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False
    # Must match (or exceed) the inner pipeline nodes' required_trust_level —
    # caller_trust_level propagates into the subgraph's state, so gating here
    # below the inner requirement would let this node's own S-1 check pass
    # while every inner node then denies it.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def get_subgraph(self) -> BaseGraph:
        from src.graph.domain_workflow_graph import StoryboardScriptWorkflowGraph

        return StoryboardScriptWorkflowGraph(config=self._parent_config())

    def extract_input(self, state: AgentState) -> str:
        """Serialize brief + platform_config as JSON for the inner graph.

        The inner graph's initial_state only carries this string as
        user_input — pre_process's validated_input/platform_config fields
        are never copied in directly, so both must travel bundled here.
        """
        validated_input = state.get("validated_input", state.get("user_input", ""))
        brief = validated_input if isinstance(validated_input, dict) else {}
        payload = {**brief, "platform_config": state.get("platform_config", {})}
        return json.dumps(payload)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "result": sub_result.get("output"),
            "compliance_report": sub_result.get("compliance_report"),
            "compliance_verdict": sub_result.get("compliance_verdict"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {}


class RetailVideoStoryboardAgent(AgentBaseGraph):
    """Cat 2 outer graph — retail product brief to compliance-checked storyboard+script.

    Domain complexity (claim extraction, storyboard, script, compliance) is
    encapsulated in the inner graph wrapped by StoryboardScriptGraphNode
    (the `main` slot). Backbone: initialize → pre_process → main →
    post_process → finalize (fixed, unmodified — add_edges() not overridden).
    """

    @property
    def name(self) -> str:
        return "ret_c2_239"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize, finalize
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = StoryboardScriptGraphNode()
        self._nodes["post_process"] = PostProcessNode()

    # add_edges() NOT overridden — framework-owned 5-node backbone with RETRY loop
