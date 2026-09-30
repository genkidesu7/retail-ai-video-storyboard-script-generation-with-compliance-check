# Test Specification

**Status**: Completed

## Test Strategy
- Coverage target: 80%
- Test types: Unit, Proof-of-Boundary, Integration

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | Pass |
| TC-02 | S-5 credential detector flags JWT-shaped strings | `detect_credentials` returns a `jwt` finding | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations (S-5 enforced in CI) | Pass |
| TC-04 | InvocationContext via configurable only | Direct access raises error | Pass |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | Pass — 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | Pass — 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | Pass — 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | Pass |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | Domain-specific input checks execute correctly (e.g. PII scan on additional fields, consent validation, business rules) | N/A — design's Security Considerations: default framework PII scan is sufficient, no node overrides `_extra_security_gate_input()` |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | Domain-specific output checks execute correctly (e.g. nested credential scan, PII re-check, content filtering, preservation verification) | N/A — design's Security Considerations: default framework credential scan is sufficient, no node overrides `_extra_security_gate_output()` |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | Pass — ≥1 per node (claim_extract, compliance_validate) |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | Pass |
| PB-3 | Level 2 → External service | Real external service connection | Data retrieved | N/A — `ComplianceKBService._call_external()` real backend not yet wired (raises `NotImplementedError`, `USE_MOCK=true` required for testing per design); covered by mock-mode + not-implemented tests instead |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | Pass |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified | Pass |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | ClaimExtractNode: keyword pre-filter runs before LLM call | Text matching prohibited-expressions list | Hit flagged `risk_level: high`, present in `state.claims` regardless of LLM output | Pass |
| BL-02 | ClaimExtractNode: empty claims list after parsing | Input with no extractable claims | `AgentStatus.ERROR` | Pass |
| BL-03 | ClaimExtractNode: LLM call failure | LLM service raises/errors | `AgentStatus.RETRY` | Pass |
| BL-04 | StoryboardDraftNode: generated duration exceeds platform max | Brief/claims producing storyboard longer than `platform_config` max duration | `AgentStatus.ERROR` (no silent truncation) | Pass |
| BL-05 | StoryboardDraftNode: chunking for long-duration videos | Long-duration brief approaching LLM context/token limits | Chunked generation strategy invoked, `state.storyboard` still valid | Pass |
| BL-06 | ScriptGenerateNode: claim left unmapped to any scene | `state.claims` containing a claim id absent from all scenes' `claim_refs` | `AgentStatus.ERROR` | Pass |
| BL-07 | ComplianceValidateNode: PASS finding without rule_citation | KB/LLM classifies as PASS but no `rule_citation` returned | Finding downgraded to `NEEDS_REVISION`, never auto-passed | Pass |
| BL-08 | ComplianceValidateNode: KB unreachable | `ComplianceKBService` raises transient/unreachable error | `AgentStatus.RETRY` up to `max_retry`, then `AgentStatus.ERROR` | Pass |
| BL-09 | ComplianceValidateNode: disclosure insertion | Scene text missing required disclosure per `disclosure_template_version` | Disclosure text inserted, `disclosure_inserted=true`, correct `disclosure_template_version` | Pass |
| BL-10 | PreProcessNode: unsupported platform | `brief.platform` not in configured `platform_config` list | `AgentStatus.ERROR` with `error_log` entry | Pass |
| BL-11 | Outer graph: inner SubgraphError propagation | Inner graph node returns RETRY/ERROR with `error_strategy="propagate"` | Outer graph surfaces `SubgraphError` as outer `AgentStatus.ERROR` | Pass |

## Test Execution Summary
- Execution date: 2026-07-07
- Total tests: 64
- Pass: 64 / Fail: 0 / Skip: 0
- Coverage: 90% (`src/`, target 80%)
