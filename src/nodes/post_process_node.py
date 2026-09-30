"""AgentCore Platform v1.0"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.security.pii_detector import detect_pii
from shared.utils.audit_logger import emit_trace_event

# Exclude the "name" heuristic: it flags any 2+ title-case words, which
# matches nearly all generated marketing copy (product names, taglines).
# See shared.security.pii_detector.detect_pii docstring on precision.
_HIGH_PRECISION_PII_TYPES = {"credit_card", "ssn_us", "my_number_jp", "email", "phone_jp", "phone_us"}


class PostProcessNode(FunctionNode):
    """Assemble the final storyboard + script + compliance document for output.

    Surfaces compliance_verdict at top level so downstream consumers can gate
    on it without parsing nested findings. Passes through upstream ERROR
    unchanged (pure formatting, no error cases of its own).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Assembling the final storyboard, script and compliance report...",
            metadata={"stage": "post_process"},
        )
        if state.get("status") == AgentStatus.ERROR.value:
            return {"status": AgentStatus.ERROR.value}

        result = state.get("result")
        compliance_report = state.get("compliance_report", {})
        compliance_verdict = state.get("compliance_verdict", "")

        formatted_output = {
            "script": result,
            "compliance_report": compliance_report,
            "compliance_verdict": compliance_verdict,
        }

        emit_trace_event(
            "output_formatted",
            {"compliance_verdict": compliance_verdict},
            state,
        )

        return {
            "formatted_output": formatted_output,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3: formatted_output is customer-facing marketing copy that may
        embed scene dialogue/on-screen text pulled from LLM generation —
        re-scan for PII the default credential scan wouldn't catch (default
        S-3 only checks credential patterns, not personal data)."""
        formatted_output = result.get("formatted_output")
        if isinstance(formatted_output, dict):
            findings = [
                f
                for f in detect_pii(json.dumps(formatted_output, default=str))
                if f["type"] in _HIGH_PRECISION_PII_TYPES
            ]
            if findings:
                raise RuntimeError(
                    f"S-3 output gate: PII pattern '{findings[0]['type']}' detected in formatted_output. "
                    "Output blocked. Remove PII from generated script content."
                )
        return result
