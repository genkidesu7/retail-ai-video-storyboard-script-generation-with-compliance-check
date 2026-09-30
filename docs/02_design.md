# Template Design Specification

**Status**: completed
**Date**: 2026-07-07
**Reviewer**: [TBD]

## Position in AgentCore Architecture

- **Agent Class**: `RetailVideoStoryboardAgent`
- **L1 Base**: AgentBaseGraph (outer) — Cat 2
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

RET-C2-239 is a **Cat 2** multi-step domain workflow. The proposal's five-step
pipeline (InputParse → ClaimExtract → StoryboardDraft → ScriptGenerate →
ComplianceValidate) is domain-specific orchestration for a single job-to-be-done
(turn a retail product brief into a compliance-checked storyboard + script), so it
is encapsulated as an **inner graph** wrapped by a `GraphNode` in the outer `main`
slot, per the Cat 2 pattern.

- Outer graph: standard AgentBaseGraph 5-node backbone (unmodified,
  `add_edges()` not overridden).
- Inner graph (`src/graph/domain_workflow_graph.py` →
  `StoryboardScriptWorkflowGraph`): inherits `BaseGraph` (fully custom linear
  topology, no pre_process/main/post_process slots) and implements the five
  domain steps as its own nodes.
- `main` slot: `StoryboardScriptGraphNode(GraphNode)` — instantiates the inner
  graph, extracts `validated_input` (the parsed brief), and merges the inner
  graph's compliance-checked output back into outer state.

### Node Configuration (outer graph)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | Validate raw brief JSON against schema; reject malformed input | `user_input` | `validated_input`, `status` | PreProcessNode |
| main | Run 4-step inner compliance pipeline (claim extract → storyboard → script → compliance validate) | `validated_input` | `result`, `compliance_report`, `status` | StoryboardScriptGraphNode (GraphNode) |
| post_process | Format final storyboard+script document, attach disclosure template version | `result`, `compliance_report` | `formatted_output`, `status` | PostProcessNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry, max 3)
                                          pre_process

Inside `main` (StoryboardScriptGraphNode → inner graph):
  START → claim_extract → storyboard_draft → script_generate → compliance_validate → END
```

Note: `pre_process` in this design only performs schema validation (brief has
required fields: product_name, claims, platform, duration). Claim extraction is a
domain LLM step and belongs in the inner graph (`claim_extract`), not in
`pre_process` — `pre_process` must stay a cheap, deterministic gate so `RETRY`
loops (bounded by `max_retry: 3`) don't re-run expensive LLM calls unnecessarily
on transient inner-graph failures reported via `ERROR`/`RETRY` status.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `brief` | `dict` | Parsed product brief (product_name, claims, platform, duration, product_category) set by `pre_process` from `validated_input` JSON | No (set by pre_process) |
| `platform_config` | `dict` | Resolved platform format spec (aspect ratio, max duration) looked up from `agent.yaml` config by platform key | No |
| `claims` | `list[dict]` | Extracted marketing claims, each `{text, category, risk_level}` classified by 景品表示法 category | No |
| `storyboard` | `list[dict]` | Scene-by-scene storyboard, each `{scene_no, visual_beat, duration_sec, claim_refs}` | No |
| `script` | `dict` | Generated script: `{scenes: list[dict with dialogue, on_screen_text, claim_refs]}` | No |
| `compliance_report` | `dict` | `{verdict, findings: list[{claim_text, rule_citation, severity, required_revision}], disclosure_inserted, disclosure_template_version}` | No |
| `compliance_verdict` | `str` | Top-level `PASS` / `FAIL` / `NEEDS_REVISION`, drives routing/output flagging | No |
| `node_history` | `Annotated[list[str], operator.add]` | Append-only trace of nodes executed (inherited from AgentState, accumulator) | Inherited |

**Field constraints:**
- All fields are flat `dict`/`list`/`str` — no Pydantic, no `datetime` (compliance
  timestamps stored as ISO 8601 strings inside `compliance_report` if needed).
- No credential-like field names; the compliance KB connection and LLM client are
  accessed via `shared/services/`, never stored in state.
- `claims`, `storyboard`, `script` are plain `list`/`dict` (replaced wholesale each
  node return) — they are not accumulator fields; only `node_history`/`error_log`
  use `Annotated[..., operator.add]` (inherited from `AgentState`).

```python
from framework.schemas.agent_state import AgentState

class State(AgentState):
    brief: dict
    platform_config: dict
    claims: list
    storyboard: list
    script: dict
    compliance_report: dict
    compliance_verdict: str
```

## Nodes

##### PreProcessNode (outer)
- **Purpose:** Validate the incoming brief JSON against the required schema
  (product_name, claims, platform, duration present and well-typed) before any
  LLM cost is incurred.
- **Input:** `state.user_input` (raw brief, JSON string or dict)
- **Output:** `state.validated_input` (normalized brief dict, JSON-serializable),
  `state.brief`, `state.status`
- **Logic:** Parse JSON if string; check required keys; reject if platform is not
  in the supported platform_config list from `agent.yaml`; strip/normalize
  free-text fields.
- **Error Cases:** Missing required field or unsupported platform →
  `AgentStatus.ERROR` + `error_log` entry; the outer backbone routes to
  `post_process`/`finalize` without invoking `main` (no LLM spend on invalid input).
- **Dependencies:** None (pure validation, no external services).

##### StoryboardScriptGraphNode (outer `main` slot, GraphNode)
- **Purpose:** Wrap the inner 4-step domain workflow; bridges outer/inner state.
- **Input:** `state.validated_input` (falls back to `user_input` per the
  GraphNode contract) via `extract_input()`.
- **Output:** `state.result`, `state.compliance_report`, `state.compliance_verdict`,
  `state.status` via `merge_output()`.
- **Logic:** `get_subgraph()` returns `StoryboardScriptWorkflowGraph()`;
  `extract_input()` returns `state.get("validated_input", state.get("user_input", ""))`;
  `merge_output()` maps inner `get_output()` fields (`output`, `compliance_report`,
  `compliance_verdict`, `status`) into outer state, returning only those changed keys.
- **Error Cases:** `error_strategy = "propagate"` — inner graph failures (e.g.
  compliance KB unreachable) raise `SubgraphError`, causing the outer node to
  return `ERROR` status; no partial/unvalidated scripts are ever surfaced.
- **Dependencies:** Inner graph; no `propagate_hitl` (HITL not in scope — see
  Security/HITL section below).

##### ClaimExtractNode (inner, `claim_extract`)
- **Purpose:** LLM identifies marketing claims in the brief and classifies each
  by 景品表示法 (Act Against Unjustifiable Premiums and Misleading Representations)
  risk category, applying a deterministic pre-filter for known prohibited
  expressions first (per proposal's hallucination mitigation).
- **Input:** `state.get("validated_input", state.get("user_input", ""))` → parsed
  as `state.brief["claims"]` (raw claim text list) and `product_category`.
- **Output:** `state.claims` (list of `{text, category, risk_level}`).
- **Logic:** 1) Run deterministic keyword pre-filter against known prohibited
  expressions list (config-driven, not LLM). 2) LLM call classifies remaining
  claims by 景品表示法 category and assigns risk_level. 3) Merge pre-filter hits
  and LLM classifications, pre-filter hits always flagged `risk_level: high`
  regardless of LLM output.
- **Error Cases:** LLM call failure → `AgentStatus.RETRY` (transient, bounded by
  `max_retry`); empty claims list after parsing → `AgentStatus.ERROR`.
- **Dependencies:** LLM service (`shared/services/llm_service` via
  `InvocationContext.credential_handle`), prohibited-expressions config list.

##### StoryboardDraftNode (inner, `storyboard_draft`)
- **Purpose:** LLM generates platform-specific scene structure (visual beats)
  calibrated to the brief's target platform format (e.g. 9:16 for TikTok Shop
  Japan).
- **Input:** `state.claims`, `state.brief` (platform, duration, product_category),
  `state.platform_config` (aspect ratio / duration limits resolved from
  `agent.yaml`).
- **Output:** `state.storyboard` (list of `{scene_no, visual_beat, duration_sec,
  claim_refs}`).
- **Logic:** LLM call generates scene breakdown honoring platform duration cap;
  each scene references claim IDs it must visually support; chunk generation by
  scene if total duration approaches LLM context/token limits (per proposal's
  Low-risk mitigation for >3 min videos).
- **Error Cases:** LLM failure → `RETRY`; generated total duration exceeds
  platform max → `ERROR` with `error_log` detail (do not silently truncate).
- **Dependencies:** LLM service; `platform_config` (from `agent.yaml`, per
  proposal's Medium-risk mitigation — parameterized, no code change needed for
  new platforms).

##### ScriptGenerateNode (inner, `script_generate`)
- **Purpose:** LLM writes dialogue and on-screen text per scene, mapping claim
  language to the scenes that carry them.
- **Input:** `state.storyboard`, `state.claims`.
- **Output:** `state.script` (`{scenes: [{scene_no, dialogue, on_screen_text,
  claim_refs}]}`).
- **Logic:** LLM call per scene (or batched) generates dialogue/on-screen text;
  every claim in `state.claims` must be mapped to at least one scene's
  `claim_refs` — validated before returning.
- **Error Cases:** LLM failure → `RETRY`; a claim left unmapped to any scene →
  `ERROR` (compliance validation downstream requires full claim traceability).
- **Dependencies:** LLM service.

##### ComplianceValidateNode (inner, `compliance_validate`)
- **Purpose:** Validate the generated script against 景品表示法 prohibited
  expressions and 消費者庁 (Consumer Affairs Agency) May 2026 AI content
  disclosure requirements; flag violations with regulatory citations; insert the
  AI disclosure template.
- **Input:** `state.script`, `state.claims`.
- **Output:** `state.compliance_report` (`{verdict, findings: [{claim_text,
  rule_citation, severity, required_revision}], disclosure_inserted,
  disclosure_template_version}`), `state.compliance_verdict`.
- **Logic:** 1) Vector KB search against the 景品表示法/消費者庁 rules corpus for
  each scene's dialogue/on-screen text. 2) LLM classifies each hit as
  violation/non-violation, **every `PASS` verdict finding must carry a
  `rule_citation`** (proposal's High-risk hallucination mitigation — no citation,
  no pass). 3) Insert 消費者庁 AI disclosure text per the current
  `disclosure_template_version` (config-pinned, per proposal's High-risk
  framework-update mitigation) if not already present.
- **Error Cases:** Compliance KB unreachable → `RETRY` (transient) up to
  `max_retry`, then `ERROR` (never silently skip compliance — no-silent-skip
  applies to regulatory checks); any finding lacking a citation is downgraded to
  `NEEDS_REVISION`, never auto-passed.
- **Dependencies:** `ComplianceKBService` (vector search), LLM service.

##### PostProcessNode (outer)
- **Purpose:** Assemble the final storyboard + script + compliance document for
  output; attach `disclosure_template_version` and overall verdict prominently.
- **Input:** `state.result`, `state.compliance_report`, `state.compliance_verdict`.
- **Output:** `state.formatted_output`, `state.status`.
- **Logic:** Merge storyboard/script/compliance findings into one structured
  output document; surface `compliance_verdict` at top level so downstream
  consumers (e.g. video-render pipeline) can gate on it without parsing nested
  findings.
- **Error Cases:** None expected (pure formatting); passes through upstream
  `ERROR` status unchanged.
- **Dependencies:** None.

## Graph Composition

**Outer graph** (`src/graph/graph.py` → `RetailVideoStoryboardAgent(AgentBaseGraph)`):
```python
class RetailVideoStoryboardAgent(AgentBaseGraph):
    @property
    def name(self) -> str:
        return "ret_c2_239"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize, finalize
        self._nodes["pre_process"]  = PreProcessNode()
        self._nodes["main"]         = StoryboardScriptGraphNode()
        self._nodes["post_process"] = PostProcessNode()
    # add_edges() NOT overridden — framework-owned backbone
```

**Inner graph** (`src/graph/domain_workflow_graph.py` →
`StoryboardScriptWorkflowGraph(BaseGraph)`), linear topology:
```
START → claim_extract → storyboard_draft → script_generate → compliance_validate → END
```

- No conditional branching inside the inner graph — each step's output is a hard
  prerequisite for the next (cannot draft a storyboard before claims are
  classified; cannot validate compliance before the script exists). `route()` is
  implemented per the `BaseGraph` ABC contract but returns the fixed next step
  (never called since no `add_conditional_edges()` is used).
- Retry semantics live at the **outer** level only: if any inner node returns
  `RETRY`, `StoryboardScriptGraphNode` propagates `SubgraphError` (per
  `error_strategy = "propagate"`), the outer graph's `main` node reports `ERROR`
  status upstream, and the outer backbone's RETRY loop re-invokes `pre_process`
  → `main` (re-running the full inner pipeline). This is acceptable because
  transient failures are expected to be rare (LLM/KB timeouts), and re-running
  the whole inner pipeline guarantees no partial/stale claim-to-scene mappings
  leak between attempts.
- Error handling path: any terminal `ERROR` from the inner graph propagates as
  `SubgraphError` → outer `main` slot reports `ERROR` → outer backbone routes
  directly to `post_process` → `finalize` (skips remaining inner steps, per
  outer 5-node backbone's standard error routing — no domain-specific override
  needed).
- Terminal node: `compliance_validate` is the last inner node; its `get_output()`
  shapes `{output, compliance_report, compliance_verdict, status, trace_id,
  correlation_id, node_history}` consumed by `StoryboardScriptGraphNode.merge_output()`.

## Services

- **LLM Service** (`shared/services/llm_service`): used by `claim_extract`,
  `storyboard_draft`, `script_generate`, `compliance_validate` (classification
  step) for all generation/classification calls. Accessed via
  `InvocationContext.credential_handle` — no raw API keys in code, state, or logs.
- **ComplianceKBService** (`src/services/service.py` →
  `ComplianceKBService`): vector KB search against the 景品表示法/消費者庁 rules
  corpus. Domain service layer only — no `agenticstar`/credential imports; calls
  into `shared/services/` for the underlying vector store connection. Refreshed
  quarterly per proposal's KB-refresh SLA mitigation (operational concern, not
  code — tracked in `docs/operation_guide.md` at stage 08).
- **Validation Service:** inlined in `PreProcessNode` (schema/platform checks are
  simple enough not to warrant a separate service file; revisit if brief schema
  grows complex).
- **External APIs:** none beyond the LLM provider and the internal compliance KB
  — no direct third-party integrations (video rendering, campaign analytics, and
  customer data handling are explicitly out of scope per the proposal).

## Security Considerations

- **Trust level:** All nodes default `required_trust_level = TrustLevel.ANONYMOUS`
  except none require elevation — this template does not perform privileged
  operations (no writes to shared customer data, no cross-template calls).
  `config/agent.yaml` sets `required_trust_level: "VERIFIED_EXTERNAL"` at the
  agent level (caller-facing gate), independent of per-node trust levels.
- **S-2 (`_extra_security_gate_input`)**: not needed beyond the framework default
  PII scan — briefs contain product/marketing text, not PII: default coverage on
  `user_input`/`validated_input` is sufficient.
- **S-3 (`_extra_security_gate_output`)**: not needed beyond the framework
  default credential scan — script/storyboard output is marketing copy with no
  credential-shaped content expected.
- **S-4 (`emit_trace_event`)**: each inner node emits one domain event —
  `claim_extract` → `"claims_classified"` (count, max risk_level); `compliance_validate`
  → `"compliance_verdict_reached"` (verdict, finding_count) for audit traceability
  of every regulatory decision (critical given ¥5M–¥50M surcharge exposure).
- **Import isolation:** `ComplianceKBService` and all node files import only
  `framework/*`, `shared/*`, and `src/*` — no `agenticstar`, no other-template
  imports.
- **HITL:** not enabled for this template (`hitl.enabled` absent/`false`).
  Compliance validation with mandatory citations is a deterministic-enough gate
  (per the "no citation, no pass" rule) that human-in-the-loop review happens
  downstream of the agent (legal sign-off remains a human step outside this
  agent's scope, per proposal's boundary — the agent replaces the *drafting*
  cycle, not final legal accountability).
- **Error handling:** `RETRY` reserved for transient failures (LLM/KB timeouts),
  bounded by `max_retry: 3` (from `agent.yaml`); `ERROR` for permanent failures
  (invalid brief schema, unmapped claims, KB unreachable after retries). No
  silent skips of compliance checks under any failure mode.

## Performance Requirements

- **Latency target:** ~15 minutes end-to-end per proposal (vs 1–2 weeks manual);
  dominated by 4 sequential LLM calls in the inner graph plus 1 KB search —
  acceptable given the 20–40× throughput goal is about parallel capacity, not
  single-invocation latency.
- **Timeout:** `agent.yaml` `config.timeout_seconds: 30` applies per node
  invocation (framework default); if inner LLM calls (especially
  `storyboard_draft`/`script_generate` for longer videos) need more headroom,
  this value should be revisited during implementation/load testing rather than
  assumed here — flagged as an open question for stage 05/06.
- **Scalability:** stateless nodes, no per-invocation mutable instance state;
  horizontal scaling is a deployment concern (out of scope for this design).
- **Token/context limits:** `storyboard_draft`/`script_generate` chunk generation
  by scene when total video duration approaches the LLM context window (proposal's
  Low-risk mitigation) — chunking strategy (batch vs per-scene calls) is an
  implementation detail for stage 06, not fixed here.

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph (outer) + BaseGraph (inner)** | Proposal is a fixed 5-step pipeline with no self-directed reasoning loop — Cat 2, not Cat 3 (matches proposal's Cat Self-Assessment). |
| Inner graph parent | BaseGraph (custom topology) | AgentBaseGraph (5-node pipeline) | **BaseGraph** | Inner steps (claim_extract → storyboard_draft → script_generate → compliance_validate) don't map onto pre_process/main/post_process; a fully custom linear topology is clearer and avoids forcing an artificial 3-slot split. |
| Claim extraction location | Outer `pre_process` | Inner graph `claim_extract` | **Inner graph** | `pre_process` must stay a cheap deterministic gate so RETRY loops don't re-run LLM calls on unrelated transient failures; claim extraction is an LLM step and belongs with the rest of the domain pipeline. |
| Retry granularity | Retry individual inner steps | Retry whole inner pipeline via outer backbone | **Whole inner pipeline (outer-level retry)** | `error_strategy="propagate"` is the framework default and simplest to reason about; per-step retry inside the inner graph would require custom retry bookkeeping not provided by `BaseGraph`, and reruns are cheap enough (~15 min budget) to tolerate full-pipeline retry on the rare transient failure. |
| HITL | Enabled (interrupt on low-confidence compliance verdict) | Disabled (deterministic citation-gated compliance) | **Disabled** | The "no citation, no pass" rule (mandatory `rule_citation` on every PASS finding) provides a deterministic-enough compliance gate without needing a human pause mid-pipeline; legal sign-off remains a separate downstream human step per the proposal's scope boundary, not an in-agent HITL interrupt. |
| Compliance KB access | Direct vector store client in node | `ComplianceKBService` in `src/services/` | **`ComplianceKBService`** | Keeps nodes free of external-integration/credential details per the service-layer convention; node calls the service, service calls `shared/services/` for the underlying connection. |
