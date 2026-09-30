"""AgentCore Platform v1.0"""

# Inner graph for the Cat 2 RetailVideoStoryboardAgent (RET-C2-239).
# Instantiated by StoryboardScriptGraphNode.get_subgraph() in src/graph/graph.py.
#
# Pipeline (fully custom, linear — no pre_process/main/post_process slots):
#   START → claim_extract → storyboard_draft → script_generate → compliance_validate → END
#
# Retry semantics live at the outer level only: any inner RETRY/ERROR propagates
# as SubgraphError (error_strategy="propagate"), and the outer backbone's RETRY
# loop re-invokes pre_process → main, re-running the full inner pipeline.

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.claim_extract_node import ClaimExtractNode
from src.nodes.compliance_validate_node import ComplianceValidateNode
from src.nodes.script_generate_node import ScriptGenerateNode
from src.nodes.storyboard_draft_node import StoryboardDraftNode
from src.schemas.state import State


class StoryboardScriptWorkflowGraph(BaseGraph):
    """Inner graph implementing the 4-step domain compliance pipeline."""

    @property
    def name(self) -> str:
        return "storyboard_script_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        """No mandatory config for this inner graph."""
        pass

    def register_nodes(self) -> None:
        """Do NOT call super() — BaseGraph.register_nodes() is abstract."""
        self._nodes["claim_extract"] = ClaimExtractNode()
        self._nodes["storyboard_draft"] = StoryboardDraftNode()
        self._nodes["script_generate"] = ScriptGenerateNode()
        self._nodes["compliance_validate"] = ComplianceValidateNode()

    def add_edges(self) -> None:
        """Fixed linear topology — every step is a hard prerequisite for the next."""
        self._sg.add_edge(START, "claim_extract")
        self._sg.add_edge("claim_extract", "storyboard_draft")
        self._sg.add_edge("storyboard_draft", "script_generate")
        self._sg.add_edge("script_generate", "compliance_validate")
        self._sg.add_edge("compliance_validate", END)

    def route(self, state: AgentState) -> str:
        """Required by BaseGraph ABC; never called (no conditional edges)."""
        return END if state.get("status") == AgentStatus.ERROR.value else "compliance_validate"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        """Shape the sub_result dict consumed by StoryboardScriptGraphNode.merge_output()."""
        return {
            "output": state.get("script"),
            "compliance_report": state.get("compliance_report"),
            "compliance_verdict": state.get("compliance_verdict"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
