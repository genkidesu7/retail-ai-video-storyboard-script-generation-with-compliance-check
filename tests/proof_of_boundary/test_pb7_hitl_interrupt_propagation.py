# PB-7: HITL Interrupt Propagation Verification
# Verifies that, when HITL is enabled, an interrupt raised inside the graph
# propagates out of the agent instead of being silently swallowed.
# This template has HITL disabled (`hitl.enabled` absent/`false` in
# config/config.yaml — see docs/02_design.md "HITL" section), so this is a
# scaffold stub per Criterion 14: it documents the boundary and is skipped
# until a future template enables HITL and provides a real interrupt case.

import os

import pytest
import yaml


def _hitl_enabled() -> bool:
    """Read hitl.enabled from config/config.yaml, defaulting to False."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.yaml")
    if not os.path.exists(config_path):
        return False

    with open(config_path, "r") as f:
        manifest = yaml.safe_load(f) or {}

    return bool(manifest.get("hitl", {}).get("enabled", False))


class TestHITLInterruptPropagation:
    """PB-7: A HITL interrupt raised inside the graph must propagate to the caller."""

    @pytest.mark.skipif(
        not _hitl_enabled(),
        reason="HITL not enabled for this template (config/config.yaml has no hitl.enabled=true); "
        "see docs/02_design.md HITL section for the scope boundary rationale.",
    )
    def test_hitl_interrupt_propagates_to_caller(self):
        pytest.fail(
            "HITL is enabled but no interrupt-propagation test has been implemented. "
            "Add a real PB-7 test exercising the interrupt path before enabling HITL."
        )
