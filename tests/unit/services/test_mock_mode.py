"""AgentCore Platform v1.0"""

from src.services.mock_mode import mock_mode_enabled


def test_mock_mode_enabled_via_use_mock(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)
    assert mock_mode_enabled() is True


def test_mock_mode_enabled_via_stg_mock_mode_alias(monkeypatch):
    """Regression test: deploy-stg sets STG_MOCK_MODE, never USE_MOCK."""
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.setenv("STG_MOCK_MODE", "true")
    assert mock_mode_enabled() is True


def test_mock_mode_disabled_when_neither_set(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)
    assert mock_mode_enabled() is False
