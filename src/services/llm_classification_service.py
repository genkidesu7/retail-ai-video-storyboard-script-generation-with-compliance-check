"""AgentCore Platform v1.0"""

# Service layer: LLM generation/classification calls shared across the inner
# domain workflow (claim_extract, storyboard_draft, script_generate,
# compliance_validate). Must NOT contain business logic or credentials.
# Nodes call this; this calls shared/services/llm for the underlying LLM client.

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from src.services.mock_mode import mock_mode_enabled

logger = logging.getLogger(__name__)

_RISK_LEVELS = ("low", "medium", "high")
_VERDICTS = ("PASS", "NEEDS_REVISION", "FAIL")
_SYSTEM_PROMPT = (
    "You are an assistant for Japanese retail marketing compliance (景品表示法 / 消費者庁 guidelines). "
    "Reply with a single JSON value and nothing else — no prose, no markdown fences."
)


class LLMResponseError(Exception):
    """Raised when the LLM reply is not valid JSON of the requested shape (maps to RETRY)."""


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM reply is not valid JSON: {exc}") from exc


def _call_llm(prompt: str, credential_handle: Any, max_tokens: int, temperature: float) -> str:
    """The one place an AzureOpenAIClient is constructed. Blocking — call via asyncio.to_thread."""
    from shared.services.llm.azure_openai_client import AzureOpenAIClient  # lazy import

    client = AzureOpenAIClient(
        config={
            "api_key": credential_handle.require("AZURE_OPENAI_API_KEY"),
            "azure_endpoint": credential_handle.require("AZURE_OPENAI_ENDPOINT"),
            "azure_deployment": credential_handle.require("AZURE_OPENAI_DEPLOYMENT"),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    )
    response = client.complete(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
    return str(response["content"])


async def _ask_json(prompt: str, invocation_context: Any, max_tokens: int = 2048, temperature: float = 0.2) -> Any:
    raw = await asyncio.to_thread(_call_llm, prompt, invocation_context.secrets, max_tokens, temperature)
    return _parse_json(raw)


def _require_list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise LLMResponseError(f"{what}: expected a JSON array, got {type(value).__name__}")
    return value


def _require_dict(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LLMResponseError(f"{what}: expected a JSON object, got {type(value).__name__}")
    return value


class LLMClassificationService:
    """LLM generation/classification for the storyboard-script inner pipeline.

    Usage from a node::

        service = LLMClassificationService()
        claims = await service.classify_claims(texts, product_category, ctx)
    """

    def __init__(self) -> None:
        self._mock_mode: bool = mock_mode_enabled()

    async def classify_claims(
        self,
        claims: list[str],
        product_category: str,
        invocation_context: Any,
    ) -> list[dict[str, Any]]:
        """Classify marketing claim texts by 景品表示法 category and risk_level."""
        if self._mock_mode:
            from src.services.mock_data import stub_classify_claims

            return await stub_classify_claims(claims, product_category)

        prompt = (
            f"Product category: {product_category}\n"
            "Classify each marketing claim by the 景品表示法 category it falls under "
            "(e.g. quality_claim, price_claim, efficacy_claim, superlative_claim) and a risk_level "
            f"of one of {list(_RISK_LEVELS)}.\n"
            'Return a JSON array with one object per claim, in order: {"text": <claim verbatim>, '
            '"category": <string>, "risk_level": <low|medium|high>}.\n'
            f"Claims (JSON): {json.dumps(claims, ensure_ascii=False)}"
        )
        items = _require_list(await _ask_json(prompt, invocation_context), "classify_claims")
        classified: list[dict[str, Any]] = []
        for item in items:
            entry = _require_dict(item, "classify_claims item")
            if entry.get("text") not in claims or entry.get("risk_level") not in _RISK_LEVELS:
                raise LLMResponseError(f"classify_claims: invalid item {entry!r}")
            classified.append(
                {"text": entry["text"], "category": str(entry.get("category", "")), "risk_level": entry["risk_level"]}
            )
        missing = [text for text in claims if text not in {c["text"] for c in classified}]
        if missing:
            raise LLMResponseError(f"classify_claims: claims missing from reply: {missing}")
        return classified

    async def generate_storyboard(
        self,
        claims: list[dict[str, Any]],
        brief: dict[str, Any],
        platform_config: dict[str, Any],
        invocation_context: Any,
    ) -> list[dict[str, Any]]:
        """Generate a platform-specific scene breakdown honoring duration caps."""
        if self._mock_mode:
            from src.services.mock_data import stub_generate_storyboard

            return await stub_generate_storyboard(claims, brief, platform_config)

        max_duration = platform_config.get("max_duration_sec", brief.get("duration", 30))
        claim_texts = [c["text"] for c in claims]
        prompt = (
            f"Product: {brief.get('product_name', '')}\n"
            f"Platform: {brief.get('platform', '')}, aspect ratio {platform_config.get('aspect_ratio', '')}.\n"
            f"Total duration must not exceed {max_duration} seconds.\n"
            "Draft a scene-by-scene storyboard in which every claim appears in at least one scene.\n"
            'Return a JSON array of scenes: {"scene_no": <int starting at 1>, "visual_beat": <string>, '
            '"duration_sec": <positive int>, "claim_refs": [<claim text verbatim>, ...]}.\n'
            f"Claims (JSON): {json.dumps(claim_texts, ensure_ascii=False)}"
        )
        items = _require_list(await _ask_json(prompt, invocation_context, max_tokens=3072), "generate_storyboard")
        scenes: list[dict[str, Any]] = []
        for item in items:
            scene = _require_dict(item, "generate_storyboard item")
            duration = scene.get("duration_sec")
            refs = scene.get("claim_refs")
            if (
                not isinstance(scene.get("scene_no"), int)
                or not isinstance(duration, int)
                or isinstance(duration, bool)
                or duration < 1
                or not isinstance(refs, list)
                or any(ref not in claim_texts for ref in refs)
            ):
                raise LLMResponseError(f"generate_storyboard: invalid scene {scene!r}")
            scenes.append(
                {
                    "scene_no": scene["scene_no"],
                    "visual_beat": str(scene.get("visual_beat", "")),
                    "duration_sec": duration,
                    "claim_refs": refs,
                }
            )
        if not scenes:
            raise LLMResponseError("generate_storyboard: reply contained no scenes")
        return scenes

    async def generate_script(
        self,
        storyboard: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        invocation_context: Any,
    ) -> dict[str, Any]:
        """Generate dialogue/on-screen text per scene, mapping claims to scenes."""
        if self._mock_mode:
            from src.services.mock_data import stub_generate_script

            return await stub_generate_script(storyboard, claims)

        prompt = (
            "Write the dialogue and on-screen text (Japanese) for each storyboard scene. "
            "Preserve each scene's claim_refs exactly as given.\n"
            'Return a JSON object: {"scenes": [{"scene_no": <int>, "dialogue": <string>, '
            '"on_screen_text": <string>, "claim_refs": [<claim text verbatim>, ...]}]}.\n'
            f"Storyboard (JSON): {json.dumps(storyboard, ensure_ascii=False)}"
        )
        result = _require_dict(await _ask_json(prompt, invocation_context, max_tokens=3072), "generate_script")
        scene_nos = {scene["scene_no"] for scene in storyboard}
        scenes: list[dict[str, Any]] = []
        for item in _require_list(result.get("scenes"), "generate_script scenes"):
            scene = _require_dict(item, "generate_script scene")
            if scene.get("scene_no") not in scene_nos or not isinstance(scene.get("claim_refs"), list):
                raise LLMResponseError(f"generate_script: invalid scene {scene!r}")
            scenes.append(
                {
                    "scene_no": scene["scene_no"],
                    "dialogue": str(scene.get("dialogue", "")),
                    "on_screen_text": str(scene.get("on_screen_text", "")),
                    "claim_refs": scene["claim_refs"],
                }
            )
        if not scenes:
            raise LLMResponseError("generate_script: reply contained no scenes")
        return {"scenes": scenes}

    async def classify_compliance_hit(
        self,
        scene_text: str,
        kb_hits: list[dict[str, Any]],
        invocation_context: Any,
    ) -> list[dict[str, Any]]:
        """Classify KB hits against scene text as violation/non-violation."""
        if self._mock_mode:
            from src.services.mock_data import stub_classify_compliance_hit

            return await stub_classify_compliance_hit(scene_text, kb_hits)

        if not kb_hits:
            return []
        allowed_citations = {hit["rule_citation"] for hit in kb_hits}
        prompt = (
            f"Scene text: {scene_text}\n"
            "For each knowledge-base rule below, decide whether the scene text violates it.\n"
            'Return a JSON array with one object per rule, in order: {"claim_text": <offending or '
            'relevant excerpt>, "rule_citation": <the rule_citation given, verbatim>, '
            '"severity": <none|low|medium|high>, "required_revision": <string, empty if none>, '
            f'"verdict": <one of {list(_VERDICTS)}>}}.\n'
            f"Rules (JSON): {json.dumps(kb_hits, ensure_ascii=False)}"
        )
        items = _require_list(await _ask_json(prompt, invocation_context), "classify_compliance_hit")
        findings: list[dict[str, Any]] = []
        for item in items:
            finding = _require_dict(item, "classify_compliance_hit item")
            if finding.get("verdict") not in _VERDICTS:
                raise LLMResponseError(f"classify_compliance_hit: invalid verdict in {finding!r}")
            # Only citations that came from the KB are trusted; a citation the LLM made up is
            # dropped so the node's "no citation, no pass" rule downgrades the finding.
            citation = finding.get("rule_citation")
            findings.append(
                {
                    "claim_text": str(finding.get("claim_text", scene_text))[:80],
                    "rule_citation": citation if citation in allowed_citations else "",
                    "severity": str(finding.get("severity", "")),
                    "required_revision": str(finding.get("required_revision", "")),
                    "verdict": finding["verdict"],
                }
            )
        return findings
