"""AgentCore Platform v1.0"""

from __future__ import annotations

import json
from typing import Any


def parse_brief_input(state: dict[str, Any]) -> dict[str, Any]:
    """Resolve the parsed brief dict from inner-graph state.

    The inner graph's initial_state only carries user_input as a JSON string
    (set by StoryboardScriptGraphNode.extract_input) — the outer pre_process
    node's validated_input dict is never copied in directly. Every inner node
    that consumes the brief must go through this helper rather than reading
    validated_input/user_input directly.
    """
    validated_input = state.get("validated_input", state.get("user_input", ""))
    if isinstance(validated_input, dict):
        return validated_input
    if isinstance(validated_input, str) and validated_input:
        try:
            parsed = json.loads(validated_input)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
