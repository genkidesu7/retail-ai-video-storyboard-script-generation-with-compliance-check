"""AgentCore Platform v1.0"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import yaml
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event

from src.nodes.brief_input import parse_brief_input

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"


def _load_prohibited_expressions() -> list[str]:
    try:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        expressions = data.get("prohibited_expressions", [])
        return [str(e) for e in expressions] if isinstance(expressions, list) else []
    except Exception:
        return []


class ClaimExtractNode(FunctionNode):
    """Inner node `claim_extract` — classifies marketing claims by 景品表示法 risk.

    Runs a deterministic keyword pre-filter against configured prohibited
    expressions first (hallucination mitigation), then calls the LLM to
    classify remaining claims. Pre-filter hits are always risk_level: high,
    regardless of what the LLM says.

    Runs inside the Cat 2 inner graph — inner initial_state only contains
    user_input, so validated_input must always fall back to user_input.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Extracting and classifying marketing claims...",
            metadata={"stage": "claim_extract"},
        )
        brief = parse_brief_input(state)
        raw_claims: list[str] = list(brief.get("claims", []))
        product_category = brief.get("product_category", "")

        if not raw_claims:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ClaimExtractNode: no claims found in brief"],
            }

        prohibited_expressions = _load_prohibited_expressions()
        prefilter_hits, remaining = self._prefilter(raw_claims, prohibited_expressions)

        ctx = InvocationContext.from_state(state)
        try:
            classified = asyncio.run(self._classify_claims(remaining, product_category, ctx))
        except Exception as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error_log": [f"ClaimExtractNode: LLM classification failed: {exc}"],
            }

        claims = prefilter_hits + classified
        if not claims:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ClaimExtractNode: empty claims list after parsing"],
            }

        max_risk = max((c["risk_level"] for c in claims), default="low")
        emit_trace_event(
            "claims_classified",
            {"count": len(claims), "max_risk_level": max_risk},
            state,
        )

        return {
            "claims": claims,
            "status": AgentStatus.SUCCESS.value,
        }

    @staticmethod
    def _prefilter(raw_claims: list[str], prohibited_expressions: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        hits: list[dict[str, Any]] = []
        remaining: list[str] = []
        for text in raw_claims:
            matched = next(
                (expr for expr in prohibited_expressions if expr and expr in text),
                None,
            )
            if matched:
                hits.append({"text": text, "category": "prohibited_expression", "risk_level": "high"})
            else:
                remaining.append(text)
        return hits, remaining

    async def _classify_claims(
        self,
        claims: list[str],
        product_category: str,
        ctx: InvocationContext,
    ) -> list[dict[str, Any]]:
        """Classify remaining claims via LLM. Credential access only via ctx.secrets."""
        if not claims:
            return []
        from src.services.llm_classification_service import LLMClassificationService

        service = LLMClassificationService()
        return await service.classify_claims(claims, product_category, ctx)
