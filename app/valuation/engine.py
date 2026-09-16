"""Safe subprocess boundary for the deterministic Node valuation calculator.

This module is locally written. It treats Node as a black-box dependency and does
not make a process-execution timing claim.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

NODE_EXECUTABLE = "node"
DEFAULT_TIMEOUT_SECONDS = 15
CALCULATOR_PATH = Path(__file__).with_name("calculator.mjs")


def run_calculator(model: Mapping[str, Any], *, verify: bool = False, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run the Node calculator with a temporary JSON model.

    Args:
        model: JSON-serializable valuation input model.
        verify: Request the calculator's G3 reproducibility verification mode.
        timeout_seconds: Positive maximum subprocess duration in seconds.

    Returns:
        Parsed calculator JSON or a structured ``status='error'`` result.
    """
    if timeout_seconds <= 0:
        return {"status": "error", "error": "timeout_seconds must be positive"}
    try:
        payload = json.dumps(dict(model), allow_nan=False)
    except (TypeError, ValueError) as exc:
        return {"status": "error", "error": f"model is not valid JSON: {exc}"}

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=True) as handle:
            handle.write(payload)
            handle.flush()
            command = [NODE_EXECUTABLE, str(CALCULATOR_PATH), handle.name]
            if verify:
                command.append("--verify")
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except FileNotFoundError:
        return {"status": "error", "error": "Node.js executable is unavailable"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "calculator timed out"}
    except OSError as exc:
        return {"status": "error", "error": f"calculator execution failed: {exc}"}

    if completed.returncode != 0:
        error_text = (completed.stderr or completed.stdout).strip()
        return {"status": "error", "error": error_text or "calculator exited unsuccessfully"}
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "error": "calculator returned invalid JSON"}
    if not isinstance(result, dict):
        return {"status": "error", "error": "calculator returned a non-object JSON result"}
    return {"status": "ok", "result": result}
