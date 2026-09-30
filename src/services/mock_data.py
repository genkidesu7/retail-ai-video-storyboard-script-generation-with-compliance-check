"""AgentCore Platform v1.0"""

# Mock stubs for USE_MOCK=true development/testing. Keep provider-agnostic —
# no real network calls, no credentials.

from __future__ import annotations

from typing import Any


async def stub_kb_search(query: str, credential_handle: str) -> list[dict[str, Any]]:
    """Mock 景品表示法/消費者庁 rule search — returns a deterministic citation."""
    return [
        {
            "rule_id": "MOCK-KEIHYOU-001",
            "rule_citation": "景品表示法第5条（優良誤認表示の禁止）",
            "matched_text": query[:80],
            "score": 0.92,
        }
    ]


async def stub_classify_claims(claims: list[str], product_category: str) -> list[dict[str, Any]]:
    """Mock LLM claim classification — deterministic medium-risk categorization."""
    return [{"text": text, "category": "quality_claim", "risk_level": "medium"} for text in claims]


async def stub_generate_storyboard(
    claims: list[dict[str, Any]],
    brief: dict[str, Any],
    platform_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Mock storyboard generation — one scene per claim, evenly split duration."""
    max_duration = platform_config.get("max_duration_sec", brief.get("duration", 30))
    scene_count = max(len(claims), 1)
    duration_per_scene = max(max_duration // scene_count, 1)
    return [
        {
            "scene_no": i + 1,
            "visual_beat": f"Scene showcasing: {claim['text'][:60]}",
            "duration_sec": duration_per_scene,
            "claim_refs": [claim["text"]],
        }
        for i, claim in enumerate(claims)
    ]


async def stub_generate_script(storyboard: list[dict[str, Any]], claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Mock script generation — one line of dialogue per scene."""
    return {
        "scenes": [
            {
                "scene_no": scene["scene_no"],
                "dialogue": f"Discover {scene['visual_beat']}",
                "on_screen_text": scene["visual_beat"][:40],
                "claim_refs": scene["claim_refs"],
            }
            for scene in storyboard
        ]
    }


async def stub_classify_compliance_hit(scene_text: str, kb_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mock compliance classification — all KB hits marked non-violation with citation."""
    return [
        {
            "claim_text": scene_text[:80],
            "rule_citation": hit["rule_citation"],
            "severity": "none",
            "required_revision": "",
            "verdict": "PASS",
        }
        for hit in kb_hits
    ]
