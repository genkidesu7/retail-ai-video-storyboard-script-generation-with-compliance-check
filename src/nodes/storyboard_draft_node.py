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

from src.nodes.brief_input import parse_brief_input


class StoryboardDraftNode(FunctionNode):
    """Inner node `storyboard_draft` — generates platform-specific scene structure.

    Honors platform duration/aspect-ratio caps resolved from config/config.yaml.
    Chunks generation by scene when total duration approaches LLM context
    limits (delegated to the service layer's chunking strategy).

    Runs inside the Cat 2 inner graph — brief and platform_config are read
    via parse_brief_input() since the inner graph only forwards user_input.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Drafting the platform-specific storyboard...",
            metadata={"stage": "storyboard_draft"},
        )
        brief = parse_brief_input(state)
        claims = state.get("claims", [])
        platform_config = brief.get("platform_config", {})

        if not claims:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["StoryboardDraftNode: no claims available to draft storyboard"],
            }

        ctx = InvocationContext.from_state(state)
        try:
            storyboard = asyncio.run(self._generate(claims, brief, platform_config, ctx))
        except Exception as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error_log": [f"StoryboardDraftNode: LLM generation failed: {exc}"],
            }

        max_duration = platform_config.get("max_duration_sec")
        total_duration = sum(scene.get("duration_sec", 0) for scene in storyboard)
        if max_duration is not None and total_duration > max_duration:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"StoryboardDraftNode: generated total duration {total_duration}s "
                    f"exceeds platform max {max_duration}s"
                ],
            }

        emit_trace_event(
            "storyboard_drafted",
            {"scene_count": len(storyboard), "total_duration_sec": total_duration},
            state,
        )

        return {
            "storyboard": storyboard,
            "status": AgentStatus.SUCCESS.value,
        }

    async def _generate(
        self,
        claims: list[dict[str, Any]],
        brief: dict[str, Any],
        platform_config: dict[str, Any],
        ctx: InvocationContext,
    ) -> list[dict[str, Any]]:
        from src.services.llm_classification_service import LLMClassificationService

        service = LLMClassificationService()
        return await service.generate_storyboard(claims, brief, platform_config, ctx)
