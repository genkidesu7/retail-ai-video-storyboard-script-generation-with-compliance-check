"""AgentCore Platform v1.0"""

import pytest


@pytest.fixture
def base_state() -> dict:
    """Minimal state fields required by InvocationContext.from_state()."""
    return {
        "correlation_id": "test-correlation-id",
        "session_id": "test-session-id",
        "thread_id": "test-thread-id",
        "trace_id": "test-trace-id",
        "caller_id": "test-caller",
        "caller_trust_level": "ANONYMOUS",
        "node_history": [],
        "error_log": [],
    }


@pytest.fixture(autouse=True)
def use_mock_mode(monkeypatch):
    """Route LLM/KB service calls through deterministic mock stubs."""
    monkeypatch.setenv("USE_MOCK", "true")
