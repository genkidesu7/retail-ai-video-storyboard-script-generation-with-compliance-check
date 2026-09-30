"""AgentCore Platform v1.0"""

# Rule 4 (.claude/rules/test_rule.md): runs the exact deploy-stg repro end to
# end — real uvicorn subprocess, deploy/invoke_payload.json, and
# scripts/stg_invoke_evidence.py — so `pytest` can answer "does deploy-stg
# pass" in seconds instead of only after pushing.

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PORT = 8199
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_health(deadline_s: float = 20.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < deadline_s:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only process env repro")
def test_stg_deploy_repro_passes_end_to_end():
    """Boots uvicorn with an env mirroring deploy-stg's job (only
    STG_MOCK_MODE + a generated INVOKE_AUTH_TOKEN — never USE_MOCK, never the
    developer's ambient shell env) and asserts stg_invoke_evidence.py reports
    overall PASS with every assertion true."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", str(REPO_ROOT / ".venv")),
        "STG_MOCK_MODE": "true",
        "INVOKE_AUTH_TOKEN": "test-token-for-repro",
    }

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        assert _wait_for_health(), (
            "server never became healthy: " + (server.stdout.read().decode(errors="replace") if server.stdout else "")
        )

        out_path = REPO_ROOT / "stage5_evidence" / "stage5_v1_repro_test.json"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/stg_invoke_evidence.py",
                "--url",
                BASE_URL,
                "--mode",
                "provisional",
                "--out",
                str(out_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        evidence = json.loads(out_path.read_text())
        assert evidence["overall"] == "PASS", evidence
        assert all(a["passed"] for a in evidence["assertions"]), evidence["assertions"]
        assert result.returncode == 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
