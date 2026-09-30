# PB-6: Invoke Execution Order Verification
# Verifies BaseNode.__call__() enforces: S-1 trust gate -> S-4 node_start ->
# S-2 _security_gate_input() -> execute() -> S-3 _security_gate_output() ->
# S-4 node_complete, for every concrete node under src/nodes/.

import importlib
import inspect
import pkgutil

import pytest

from framework.nodes.graph_node import GraphNode

# GraphNode subclasses wrap a real subgraph invocation — a bare-minimum state
# makes the subgraph legitimately fail (ERROR), which is correct propagate
# behavior, not an invoke-order violation. They need domain-shaped input to
# exercise the success path this test asserts on.
_GRAPH_NODE_EXTRA_STATE = {
    "validated_input": {
        "product_name": "p",
        "claims": ["Improves texture"],
        "platform": "tiktok_shop_jp",
        "duration": 30,
        "product_category": "skincare",
    },
    "platform_config": {"aspect_ratio": "9:16", "max_duration_sec": 60},
}


def _discover_node_classes() -> list[type]:
    """Import every module under src/nodes/ and collect concrete BaseNode subclasses."""
    from framework.nodes.base_node import BaseNode

    try:
        pkg = importlib.import_module("src.nodes")
    except ImportError:
        return []

    discovered = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="src.nodes."):
        module = importlib.import_module(modname)
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseNode)
                and attr is not BaseNode
                and attr.__module__ == modname
                and not inspect.isabstract(attr)
            ):
                discovered.append(attr)
    return discovered


class TestInvokeOrder:
    """PB-6: __call__ must run S-1 -> node_start -> S-2 -> execute() -> S-3 -> node_complete."""

    def test_call_order_for_every_node(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "true")
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        import framework.nodes.base_node as base_node_module

        failures: list[str] = []
        for node_cls in node_classes:
            order: list[str] = []
            monkeypatch.setattr(
                base_node_module,
                "emit_trace_event",
                lambda event_type, _payload, _state, _o=order: _o.append(f"event:{event_type}"),
            )

            for method_name, label in (
                ("_security_gate_input", "security_gate_input"),
                ("execute", "execute"),
                ("_security_gate_output", "security_gate_output"),
            ):
                original = getattr(node_cls, method_name)

                def spy(self, arg, _o=order, _label=label, _orig=original):
                    _o.append(_label)
                    return _orig(self, arg)

                monkeypatch.setattr(node_cls, method_name, spy)

            instance = node_cls()
            state = {
                "caller_trust_level": node_cls.required_trust_level.value,
                "correlation_id": "pb6-invoke-order-test",
                "session_id": "pb6-session",
                "thread_id": "pb6-thread",
                "trace_id": "pb6-trace",
            }
            if issubclass(node_cls, GraphNode):
                state.update(_GRAPH_NODE_EXTRA_STATE)
            instance(state)

            if issubclass(node_cls, GraphNode):
                # GraphNode.execute() invokes a real subgraph whose own nodes
                # emit their own node_start/node_complete via the same shared
                # emit_trace_event — only this node's own S-2/execute/S-3
                # bracket (first/last events) is asserted, not the full trace.
                own_events = [order[0], order[1], order[2], order[-2], order[-1]]
                expected = [
                    "event:node_start",
                    "security_gate_input",
                    "execute",
                    "security_gate_output",
                    "event:node_complete",
                ]
                if own_events != expected:
                    failures.append(
                        f"{node_cls.__name__}: invoke order violation.\n"
                        f"expected bracket: {expected}\nactual bracket:   {own_events}"
                    )
                continue

            expected = [
                "event:node_start",
                "security_gate_input",
                "execute",
                "security_gate_output",
                "event:node_complete",
            ]
            if order != expected:
                failures.append(
                    f"{node_cls.__name__}: invoke order violation.\n" f"expected: {expected}\nactual:   {order}"
                )

        assert not failures, "\n\n".join(failures)
