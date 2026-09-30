"""AGENTIC STAR Marketplace entrypoint — one-shot Pod process.

Referenced by agenticstar-deploy/Dockerfile's `CMD ["python", "cli.py"]`. Compiles
the agent, provisions its secrets, then hands off to
shared.bootstrap.marketplace_app for the Marketplace lifecycle (identity,
input, events, terminal delivery, exit).
"""

from pathlib import Path

from framework.utils.config_loader import load_agent_config
from shared.bootstrap.marketplace_app import run_agent_marketplace

from src.graph.graph import RetailVideoStoryboardAgent

if __name__ == "__main__":
    run_agent_marketplace(
        RetailVideoStoryboardAgent,
        agent_name="RET-C2-239",
        namespace="RET",
        config=load_agent_config(Path(__file__).resolve().parent),
    )
