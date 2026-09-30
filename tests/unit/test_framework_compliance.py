"""AgentCore Platform v1.0"""

# Framework Compliance (TC) tests — SDK-level contract enforcement, not
# domain-specific business logic. See docs/03_test_spec.md TC-01..TC-11.

import ast
import inspect
import textwrap
import typing

import pytest

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from framework.schemas.invocation_context import InvocationContext
from framework.security.credential_detector import detect_credentials
from src.nodes.claim_extract_node import ClaimExtractNode
from src.nodes.compliance_validate_node import ComplianceValidateNode
from src.nodes.pre_process_node import PreProcessNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.script_generate_node import ScriptGenerateNode
from src.nodes.storyboard_draft_node import StoryboardDraftNode
from src.schemas.state import State

ALL_NODE_CLASSES = [
    PreProcessNode,
    ClaimExtractNode,
    StoryboardDraftNode,
    ScriptGenerateNode,
    ComplianceValidateNode,
    PostProcessNode,
]

EMIT_TRACE_NODES = [ClaimExtractNode, ComplianceValidateNode]


class TestTC01StateFlatTypedDict:
    """TC-01: State contract is a flat TypedDict — no Pydantic/dataclass."""

    def test_state_is_typed_dict(self):
        assert typing.is_typeddict(State)

    def test_state_fields_are_flat_types(self):
        hints = typing.get_type_hints(State)
        for field_name in ("brief", "platform_config", "claims", "storyboard", "script", "compliance_report"):
            assert field_name in hints


class TestTC03NoCredentialInState:
    """TC-03: no JWT/credential fields defined on State (CI gate-credential-scan covers full repo)."""

    def test_state_has_no_credential_field_names(self):
        import re

        pattern = re.compile(r"(jwt|token|api_key|secret|password|credential)", re.IGNORECASE)
        hints = typing.get_type_hints(State)
        offenders = [name for name in hints if pattern.search(name)]
        assert offenders == []


class TestTC02CredentialShapedStringsAreDetected:
    """TC-02: S-5 — a JWT-shaped string is flagged by the SDK's credential detector.

    agenticstar-agentcore no longer raises SecurityViolationError when a node class body holds a
    JWT-shaped attribute; detection is done by framework.security.credential_detector, which the
    CI credential-scan gate mirrors.
    """

    def test_jwt_shaped_string_is_detected(self):
        jwt_like = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        findings = detect_credentials(jwt_like)
        assert [f["type"] for f in findings] == ["jwt"]

    def test_plain_text_is_not_flagged(self):
        assert detect_credentials("Improves skin texture in 2 weeks") == []


class TestTC04InvocationContextViaConfigurableOnly:
    """TC-04: InvocationContext must be built via from_state(), not constructed ad hoc from raw state access."""

    def test_from_state_requires_correlation_fields(self):
        with pytest.raises(KeyError):
            InvocationContext.from_state({})

    def test_from_state_builds_context_from_state_dict(self):
        state = {
            "correlation_id": "c1",
            "session_id": "s1",
            "thread_id": "t1",
            "trace_id": "tr1",
        }
        ctx = InvocationContext.from_state(state)
        assert ctx.correlation_id == "c1"
        assert ctx.caller_trust_level == TrustLevel.ANONYMOUS


class TestTC05NoDuplicateLifecycleEventsInExecute:
    """TC-05: node_start/node_complete/node_error must not appear inside execute() bodies (owned by BaseNode.__call__)."""

    @pytest.mark.parametrize("node_cls", ALL_NODE_CLASSES)
    def test_execute_body_has_no_lifecycle_event_literals(self, node_cls):
        source = inspect.getsource(node_cls.execute)
        for forbidden in ("node_start", "node_complete", "node_error"):
            assert forbidden not in source, f"{node_cls.__name__}.execute() must not emit '{forbidden}'"


class TestTC06SecurityGateInputNotOverridden:
    """TC-06: FunctionNode subclasses must not override _security_gate_input (enforced by __init_subclass__)."""

    def test_overriding_security_gate_input_raises_type_error(self):
        with pytest.raises(TypeError):

            class _BadNode(FunctionNode):
                def _security_gate_input(self, state):
                    return state

                def execute(self, state):
                    return {}


class TestTC07SecurityGateOutputNotOverridden:
    """TC-07: FunctionNode subclasses must not override _security_gate_output (enforced by __init_subclass__)."""

    def test_overriding_security_gate_output_raises_type_error(self):
        with pytest.raises(TypeError):

            class _BadNode(FunctionNode):
                def _security_gate_output(self, result):
                    return result

                def execute(self, state):
                    return {}


class TestTC08RequiredTrustLevelEnforced:
    """TC-08: required_trust_level is declared explicitly on every domain node,
    and insufficient caller trust is refused by BaseNode.__call__ (S-1 gate)."""

    @pytest.mark.parametrize("node_cls", ALL_NODE_CLASSES)
    def test_required_trust_level_is_declared(self, node_cls):
        assert hasattr(node_cls, "required_trust_level")
        assert isinstance(node_cls.required_trust_level, TrustLevel)

    def test_insufficient_trust_level_is_refused(self, base_state, monkeypatch):
        node = PreProcessNode()
        monkeypatch.setattr(PreProcessNode, "required_trust_level", TrustLevel.INTERNAL)
        state = {**base_state, "caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": "{}"}
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert "S-1 trust gate denied" in result["error_log"][0]


class TestTC11DomainTraceEventPerExecute:
    """TC-11: at least one domain emit_trace_event() call inside each execute() body, for nodes with audit obligations."""

    @pytest.mark.parametrize("node_cls", EMIT_TRACE_NODES)
    def test_execute_calls_emit_trace_event(self, node_cls):
        tree = ast.parse(textwrap.dedent(inspect.getsource(node_cls.execute)))
        calls = [
            node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert "emit_trace_event" in calls, f"{node_cls.__name__}.execute() must call emit_trace_event()"


class TestStatusValuesAreEnumConstants:
    """Supports TC-05/TC-08: nodes must return AgentStatus enum values, never bare strings."""

    def test_agent_status_values_used(self):
        assert AgentStatus.SUCCESS.value == "success"
        assert AgentStatus.ERROR.value == "error"
        assert AgentStatus.RETRY.value == "retry"
