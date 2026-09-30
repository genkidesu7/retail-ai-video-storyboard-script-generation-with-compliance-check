"""AgentCore Platform v1.0"""

# Shared mock-mode flag resolution. Every service that gates real-vs-mock
# behavior must import mock_mode_enabled() instead of re-deriving this logic —
# see .claude/rules/implementation_rule.md §1.

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

_env: dict[str, str | None] = dotenv_values(Path(__file__).parent.parent.parent / ".env")


def _get_flag(key: str) -> str:
    """OS env takes precedence over .env file."""
    return os.environ.get(key) or _env.get(key) or ""


def mock_mode_enabled() -> bool:
    """True if mock mode is on via either accepted alias.

    USE_MOCK is the canonical flag (what tests set). STG_MOCK_MODE is what
    the deploy-stg CI job actually exports to the uvicorn process — both must
    be checked here so every caller inherits the guarantee.
    """
    for key in ("USE_MOCK", "STG_MOCK_MODE"):
        if _get_flag(key).lower() in ("1", "true", "yes"):
            return True
    return False
