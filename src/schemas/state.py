"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict — never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects
# cause silent corruption.  Extend AgentState with agent-specific
# fields only.  Do NOT add credentials, secrets, or Pydantic models.

from typing import Any

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for RetailVideoStoryboardAgent (RET-C2-239).

    All shared fields (user_input, status, session_id, node_history,
    error_log, hitl_*, etc.) are inherited from AgentState.
    """

    brief: dict[str, Any]
    """Parsed product brief set by pre_process from validated_input JSON.
    Shape: {product_name: str, claims: list[str], platform: str,
    duration: int, product_category: str}."""

    platform_config: dict[str, Any]
    """Resolved platform format spec looked up from config/config.yaml by platform key.
    Shape: {aspect_ratio: str, max_duration_sec: int}."""

    claims: list[dict[str, Any]]
    """Extracted marketing claims classified by 景品表示法 category.
    Shape: list[{text: str, category: str, risk_level: str}]."""

    storyboard: list[dict[str, Any]]
    """Scene-by-scene storyboard.
    Shape: list[{scene_no: int, visual_beat: str, duration_sec: int,
    claim_refs: list[str]}]."""

    script: dict[str, Any]
    """Generated dialogue/on-screen text per scene.
    Shape: {scenes: list[{scene_no: int, dialogue: str, on_screen_text: str,
    claim_refs: list[str]}]}."""

    compliance_report: dict[str, Any]
    """Compliance validation findings and disclosure state.
    Shape: {verdict: str, findings: list[{claim_text: str, rule_citation: str,
    severity: str, required_revision: str}], disclosure_inserted: bool,
    disclosure_template_version: str}."""

    compliance_verdict: str
    """Top-level PASS / FAIL / NEEDS_REVISION verdict, drives routing/output flagging."""
