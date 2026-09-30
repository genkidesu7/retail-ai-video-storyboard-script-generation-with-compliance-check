"""AgentCore Platform v1.0"""

# Node contract (agents_layer_design.md §1):
#  - Extend FunctionNode; implement execute(state) -> dict
#  - Return ONLY the fields this node changes (never full state)
#  - Return AgentStatus enum constants — never plain strings [A1]
#  - Read input_context via state.get("input_context", {}) — read-only [C1]
#  - Never import from mediator/, api/, or other agents

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.utils.config_loader import load_config
from shared.utils.audit_logger import emit_trace_event

_REQUIRED_KEYS = ("product_name", "claims", "platform", "duration")
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"

_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "system prompt",
    "you are now",
    "act as",
    "<|im_start|>",
    "[system]",
)


class PreProcessNode(FunctionNode):
    """Validate the incoming brief JSON against the required schema.

    Cheap, deterministic gate only — no LLM calls — so the outer RETRY loop
    (max_retry: 3) does not re-run expensive LLM work on unrelated transient
    failures from the inner (main) graph.
    """

    # S-1: explicit by design, not inherited implicitly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Validating the incoming brief...",
            metadata={"stage": "pre_process"},
        )
        user_input = state.get("user_input", "")

        if not user_input or (isinstance(user_input, str) and not user_input.strip()):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: user_input is empty or missing"],
            }

        brief = self._parse_brief(user_input)
        if brief is None:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: user_input is not valid JSON or a dict"],
            }

        missing = [key for key in _REQUIRED_KEYS if key not in brief]
        if missing:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"PreProcessNode: missing required field(s): {', '.join(missing)}"],
            }

        platform = brief.get("platform")
        supported_platforms = self._supported_platform_config()
        if platform not in supported_platforms:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"PreProcessNode: unsupported platform '{platform}'. " f"Supported: {sorted(supported_platforms)}"
                ],
            }

        normalized_brief = {
            "product_name": str(brief["product_name"]).strip(),
            "claims": list(brief["claims"]),
            "platform": str(platform).strip(),
            "duration": brief["duration"],
            "product_category": str(brief.get("product_category", "")).strip(),
        }

        emit_trace_event(
            "brief_validated",
            {"platform": normalized_brief["platform"]},
            state,
        )

        return {
            "validated_input": normalized_brief,
            "brief": normalized_brief,
            "platform_config": supported_platforms[platform],
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2: brief text carries product/marketing copy from an external
        caller — scan for prompt-injection attempts before it reaches the LLM
        pipeline (default PII scan only masks PII, not instruction-override text)."""
        user_input = state.get("user_input", "")
        text = user_input if isinstance(user_input, str) else json.dumps(user_input)
        hit = self._detect_injection(text)
        if hit:
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = [
                *state.get("error_log", []),
                f"PreProcessNode: potential prompt injection detected ('{hit}')",
            ]
        return state

    @staticmethod
    def _detect_injection(text: str) -> str | None:
        lowered = text.lower()
        for pattern in _INJECTION_PATTERNS:
            if pattern in lowered:
                return pattern
        return None

    @staticmethod
    def _parse_brief(user_input: Any) -> dict[str, Any] | None:
        if isinstance(user_input, dict):
            return user_input
        if isinstance(user_input, str):
            try:
                parsed = json.loads(user_input)
            except (json.JSONDecodeError, TypeError):
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    @staticmethod
    def _supported_platform_config() -> dict[str, dict[str, Any]]:
        config = load_config(str(_CONFIG_PATH))
        platforms = config.get("platform_config", {})
        return platforms if isinstance(platforms, dict) else {}
