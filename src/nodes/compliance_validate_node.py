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

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"
_DEFAULT_DISCLOSURE_TEMPLATE_VERSION = "2026-05-01"
_DISCLOSURE_TEXT = (
    "本コンテンツはAIにより生成されています。"  # This content is AI-generated.
    "（消費者庁ガイドライン準拠 / Consumer Affairs Agency disclosure）"
)


def _load_disclosure_template_version() -> str:
    try:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        version = data.get("disclosure_template_version")
        return str(version) if version else _DEFAULT_DISCLOSURE_TEMPLATE_VERSION
    except Exception:
        return _DEFAULT_DISCLOSURE_TEMPLATE_VERSION


class ComplianceValidateNode(FunctionNode):
    """Inner node `compliance_validate` — final inner-graph step.

    Searches ComplianceKBService for each scene's dialogue/on-screen text,
    classifies hits via LLM, enforces "no citation, no pass", and inserts
    the 消費者庁 AI disclosure text per the config-pinned template version.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the script against 景品表示法 / 消費者庁 rules...",
            metadata={"stage": "compliance_validate"},
        )
        script = state.get("script", {})
        scenes = script.get("scenes", [])

        if not scenes:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ComplianceValidateNode: no script scenes to validate"],
            }

        ctx = InvocationContext.from_state(state)
        try:
            findings = asyncio.run(self._validate_scenes(scenes, ctx))
        except Exception as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error_log": [f"ComplianceValidateNode: compliance KB unreachable: {exc}"],
            }

        disclosure_template_version = _load_disclosure_template_version()
        disclosure_inserted = self._ensure_disclosure(scenes)

        verdict = self._overall_verdict(findings)
        compliance_report = {
            "verdict": verdict,
            "findings": findings,
            "disclosure_inserted": disclosure_inserted,
            "disclosure_template_version": disclosure_template_version,
        }

        emit_trace_event(
            "compliance_verdict_reached",
            {"verdict": verdict, "finding_count": len(findings)},
            state,
        )

        return {
            "compliance_report": compliance_report,
            "compliance_verdict": verdict,
            "status": AgentStatus.SUCCESS.value,
        }

    async def _validate_scenes(self, scenes: list[dict[str, Any]], ctx: InvocationContext) -> list[dict[str, Any]]:
        from src.services.service import ComplianceKBService
        from src.services.llm_classification_service import LLMClassificationService

        from src.services.mock_mode import mock_mode_enabled

        kb_service = ComplianceKBService()
        llm_service = LLMClassificationService()
        credential_handle = "mock" if mock_mode_enabled() else ctx.secrets.require("AZURE_OPENAI_API_KEY")

        findings: list[dict[str, Any]] = []
        for scene in scenes:
            scene_text = f"{scene.get('dialogue', '')} {scene.get('on_screen_text', '')}".strip()
            kb_hits = await kb_service.search(scene_text, credential_handle)
            classified = await llm_service.classify_compliance_hit(scene_text, kb_hits, ctx)
            for finding in classified:
                findings.append(self._enforce_citation_rule(finding))
        return findings

    @staticmethod
    def _enforce_citation_rule(finding: dict[str, Any]) -> dict[str, Any]:
        """No citation, no pass — downgrade any PASS lacking rule_citation."""
        if finding.get("verdict") == "PASS" and not finding.get("rule_citation"):
            finding = dict(finding)
            finding["verdict"] = "NEEDS_REVISION"
            finding["severity"] = finding.get("severity") or "medium"
            finding["required_revision"] = (
                finding.get("required_revision") or "Missing rule citation — manual review required"
            )
        return finding

    @staticmethod
    def _overall_verdict(findings: list[dict[str, Any]]) -> str:
        verdicts = {f.get("verdict") for f in findings}
        if "FAIL" in verdicts:
            return "FAIL"
        if "NEEDS_REVISION" in verdicts:
            return "NEEDS_REVISION"
        return "PASS"

    @staticmethod
    def _ensure_disclosure(scenes: list[dict[str, Any]]) -> bool:
        already_present = any(_DISCLOSURE_TEXT in scene.get("on_screen_text", "") for scene in scenes)
        if already_present:
            return True
        if scenes:
            scenes[-1]["on_screen_text"] = f"{scenes[-1].get('on_screen_text', '')} {_DISCLOSURE_TEXT}".strip()
        return True
