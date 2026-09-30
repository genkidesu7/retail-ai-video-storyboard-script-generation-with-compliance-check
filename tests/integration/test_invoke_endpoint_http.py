"""AgentCore Platform v1.0"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.server import _lifespan, app

VALID_BRIEF = json.dumps(
    {
        "product_name": "Glow Serum",
        "claims": ["Improves skin texture"],
        "platform": "tiktok_shop_jp",
        "duration": 30,
    }
)


@pytest.mark.asyncio
async def test_invoke_endpoint_succeeds_over_http(monkeypatch):
    """Regression test: agent.invoke() is sync and its nodes call asyncio.run()
    internally. Calling it directly from an async route (without to_thread)
    raises 'asyncio.run() cannot be called from a running event loop' inside
    the node, which the node's except-Exception silently turns into
    status: "error" — a 200 response with no visible crash. An in-process
    sync call to agent.invoke() never exercises this path."""
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.setenv("INVOKE_AUTH_TOKEN", "test-token")
    transport = ASGITransport(app=app)
    # ASGITransport does not trigger the lifespan, so compile/provision the agent manually.
    async with _lifespan(app), AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/invoke", json={"input": VALID_BRIEF}, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_invoke_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.setenv("INVOKE_AUTH_TOKEN", "test-token")
    transport = ASGITransport(app=app)
    async with _lifespan(app), AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/invoke", json={"input": VALID_BRIEF}, headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint_over_http():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
