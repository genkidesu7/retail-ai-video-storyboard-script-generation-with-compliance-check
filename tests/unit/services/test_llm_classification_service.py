"""AgentCore Platform v1.0"""

# Real (non-mock) path of LLMClassificationService. Only the AzureOpenAIClient network
# boundary is faked; prompt handling, JSON parsing and validation run for real.

import json
from types import SimpleNamespace

import pytest
from framework.secrets.base import MissingSecret
from shared.secrets.inmemory_provider import InMemoryProvider

from src.services import llm_classification_service as svc
from src.services.llm_classification_service import LLMClassificationService, LLMResponseError

_SECRETS = {
    "AZURE_OPENAI_API_KEY": "k",
    "AZURE_OPENAI_ENDPOINT": "https://example.services.ai.azure.com",
    "AZURE_OPENAI_DEPLOYMENT": "dep",
}


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)


@pytest.fixture
def ctx():
    return SimpleNamespace(secrets=InMemoryProvider(_SECRETS))


@pytest.fixture
def reply(monkeypatch):
    """Make the fake Azure client answer with a fixed string; records the config it was built with."""
    seen: dict = {}

    def _set(content: str):
        class _Client:
            def __init__(self, config):
                seen["config"] = config

            def complete(self, messages):
                seen["messages"] = messages
                return {"content": content}

        monkeypatch.setattr("shared.services.llm.azure_openai_client.AzureOpenAIClient", _Client)
        return seen

    return _set


class TestClassifyClaims:
    async def test_parses_valid_reply_and_builds_client_from_secrets(self, reply, ctx):
        seen = reply(json.dumps([{"text": "a", "category": "quality_claim", "risk_level": "high"}]))
        result = await LLMClassificationService().classify_claims(["a"], "food", ctx)
        assert result == [{"text": "a", "category": "quality_claim", "risk_level": "high"}]
        assert seen["config"]["api_key"] == "k"
        assert seen["config"]["azure_deployment"] == "dep"

    async def test_accepts_markdown_fenced_json(self, reply, ctx):
        reply('```json\n[{"text": "a", "category": "c", "risk_level": "low"}]\n```')
        result = await LLMClassificationService().classify_claims(["a"], "food", ctx)
        assert result[0]["risk_level"] == "low"

    async def test_non_json_reply_raises(self, reply, ctx):
        reply("sorry, I cannot help")
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().classify_claims(["a"], "food", ctx)

    async def test_invalid_risk_level_raises(self, reply, ctx):
        reply(json.dumps([{"text": "a", "category": "c", "risk_level": "extreme"}]))
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().classify_claims(["a"], "food", ctx)

    async def test_dropped_claim_raises(self, reply, ctx):
        reply(json.dumps([{"text": "a", "category": "c", "risk_level": "low"}]))
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().classify_claims(["a", "b"], "food", ctx)

    async def test_missing_secret_fails_fast(self, reply):
        reply("[]")
        bare = SimpleNamespace(secrets=InMemoryProvider({}))
        with pytest.raises(MissingSecret):
            await LLMClassificationService().classify_claims(["a"], "food", bare)


class TestGenerateStoryboard:
    async def test_valid_scenes(self, reply, ctx):
        scenes = [{"scene_no": 1, "visual_beat": "b", "duration_sec": 10, "claim_refs": ["a"]}]
        reply(json.dumps(scenes))
        result = await LLMClassificationService().generate_storyboard(
            [{"text": "a"}], {"product_name": "p"}, {"max_duration_sec": 30}, ctx
        )
        assert result == scenes

    async def test_claim_ref_not_in_claims_raises(self, reply, ctx):
        reply(json.dumps([{"scene_no": 1, "visual_beat": "b", "duration_sec": 10, "claim_refs": ["zzz"]}]))
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().generate_storyboard([{"text": "a"}], {}, {}, ctx)

    async def test_non_positive_duration_raises(self, reply, ctx):
        reply(json.dumps([{"scene_no": 1, "visual_beat": "b", "duration_sec": 0, "claim_refs": ["a"]}]))
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().generate_storyboard([{"text": "a"}], {}, {}, ctx)


class TestGenerateScript:
    async def test_valid_script(self, reply, ctx):
        reply(json.dumps({"scenes": [{"scene_no": 1, "dialogue": "d", "on_screen_text": "t", "claim_refs": ["a"]}]}))
        storyboard = [{"scene_no": 1, "visual_beat": "b", "duration_sec": 5, "claim_refs": ["a"]}]
        result = await LLMClassificationService().generate_script(storyboard, [{"text": "a"}], ctx)
        assert result["scenes"][0]["dialogue"] == "d"

    async def test_unknown_scene_no_raises(self, reply, ctx):
        reply(json.dumps({"scenes": [{"scene_no": 9, "dialogue": "d", "on_screen_text": "t", "claim_refs": []}]}))
        storyboard = [{"scene_no": 1, "visual_beat": "b", "duration_sec": 5, "claim_refs": ["a"]}]
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().generate_script(storyboard, [{"text": "a"}], ctx)


class TestClassifyComplianceHit:
    _HITS = [{"rule_id": "R1", "rule_citation": "景品表示法第5条", "matched_text": "x", "score": 0.9}]

    async def test_kb_citation_is_kept(self, reply, ctx):
        reply(
            json.dumps(
                [
                    {
                        "claim_text": "x",
                        "rule_citation": "景品表示法第5条",
                        "severity": "high",
                        "required_revision": "remove",
                        "verdict": "FAIL",
                    }
                ]
            )
        )
        result = await LLMClassificationService().classify_compliance_hit("x", self._HITS, ctx)
        assert result[0]["rule_citation"] == "景品表示法第5条"
        assert result[0]["verdict"] == "FAIL"

    async def test_invented_citation_is_dropped(self, reply, ctx):
        reply(json.dumps([{"claim_text": "x", "rule_citation": "made up law", "severity": "none", "verdict": "PASS"}]))
        result = await LLMClassificationService().classify_compliance_hit("x", self._HITS, ctx)
        assert result[0]["rule_citation"] == ""

    async def test_invalid_verdict_raises(self, reply, ctx):
        reply(json.dumps([{"claim_text": "x", "rule_citation": "景品表示法第5条", "verdict": "MAYBE"}]))
        with pytest.raises(LLMResponseError):
            await LLMClassificationService().classify_compliance_hit("x", self._HITS, ctx)

    async def test_no_kb_hits_makes_no_llm_call(self, ctx):
        assert await LLMClassificationService().classify_compliance_hit("x", [], ctx) == []


def test_parse_json_rejects_garbage():
    with pytest.raises(LLMResponseError):
        svc._parse_json("not json")
