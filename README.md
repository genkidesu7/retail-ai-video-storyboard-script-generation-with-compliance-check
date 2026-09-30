# RET-C2-239 — Retail AI Video Storyboard & Script Generation with Compliance Check

> **Category**: Cat 2 (Multi-step Job Orchestration)
> **Industry**: Retail (RET)

## Overview

RET-C2-239 is a multi-step AI agent that turns a retail product brief into a storyboard and video script for AI-generated video campaigns in the Japanese market, and checks the result against Japanese advertising rules (景品表示法 and 消費者庁 guidelines). It runs a four-step pipeline:

- **Claim extraction** — classifies each marketing claim by regulatory category and risk level; expressions on the configured prohibited list are always marked high risk.
- **Storyboard drafting** — builds a scene breakdown that respects each platform's aspect ratio and maximum duration (TikTok Shop, Instagram Reels, YouTube Shorts).
- **Script generation** — writes dialogue and on-screen text per scene and maps every claim to a scene.
- **Compliance validation** — checks each scene against rule citations, returns a `PASS` / `NEEDS_REVISION` / `FAIL` verdict with the rule cited for each finding (a finding without a citation cannot pass), and inserts the AI-generated-content disclosure text.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency (`openai` and `marketplace` extras, pinned in `pyproject.toml`). |
| **Azure OpenAI** | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT`, provided as secrets, for non-mock runs. |
| Python | >= 3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration (agent.yaml manifest, config.yaml runtime settings)
docs/         design and test specification
```

See `docs/` for the design (`02_design.md`) and the test specification (`03_test_spec.md`).

## Customising

1. Adjust `config/` for your own environment and policies — platform limits, the prohibited-expression list and the disclosure template version live in `config/config.yaml`.
2. Replace the knowledge sources and sample data with your own. The compliance rules corpus is served by sample data in `src/services/mock_data.py`; connect your own rules source in `src/services/service.py`.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.

---
