"""AgentCore Platform v1.0"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event


class ScriptGenerateNode(FunctionNode):
    """Inner node `script_generate` — writes dialogue and on-screen text per scene.

    Validates every claim in state.claims maps to at least one scene's
    claim_refs before returning — compliance validation downstream requires
    full claim traceability.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Generating dialogue and on-screen text...",
            metadata={"stage": "script_generate"},
        )
        storyboard = state.get("storyboard", [])
        claims = state.get("claims", [])

        if not storyboard:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ScriptGenerateNode: no storyboard available to generate script"],
            }

        ctx = InvocationContext.from_state(state)
        try:
            script = asyncio.run(self._generate(storyboard, claims, ctx))
        except Exception as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error_log": [f"ScriptGenerateNode: LLM generation failed: {exc}"],
            }

        unmapped = self._find_unmapped_claims(claims, script)
        if unmapped:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"ScriptGenerateNode: claim(s) not mapped to any scene: {unmapped}"],
            }

        emit_trace_event(
            "script_generated",
            {"scene_count": len(script.get("scenes", []))},
            state,
        )

        return {
            "script": script,
            "status": AgentStatus.SUCCESS.value,
        }

    async def _generate(
        self,
        storyboard: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        ctx: InvocationContext,
    ) -> dict[str, Any]:
        from src.services.llm_classification_service import LLMClassificationService

        service = LLMClassificationService()
        return await service.generate_script(storyboard, claims, ctx)

    @staticmethod
    def _find_unmapped_claims(claims: list[dict[str, Any]], script: dict[str, Any]) -> list[str]:
        mapped_refs: set[str] = set()
        for scene in script.get("scenes", []):
            mapped_refs.update(scene.get("claim_refs", []))
        return [c["text"] for c in claims if c.get("text") not in mapped_refs]
