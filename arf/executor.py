"""The only execution boundary in VS-001: the packaged fixed demo worker."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

from arf.models import ARFError, json_text, validate_input


TIMEOUT_SECONDS = 5.0
OUTPUT_LIMIT = 4096


@dataclass(frozen=True)
class WorkerOutput:
    stdout: str
    stderr: str
    exit_code: int


def execute_demo(input_data: dict) -> WorkerOutput:
    validate_input(input_data)
    try:
        process = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("worker.py").resolve())],
            input=json_text(input_data),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            # Do not pass credentials or Python customization to the worker.
            env={},
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ARFError(f"demo worker timed out after {TIMEOUT_SECONDS:g} seconds") from exc
    if len(process.stdout) > OUTPUT_LIMIT or len(process.stderr) > OUTPUT_LIMIT:
        raise ARFError("demo worker exceeded output limit")
    return WorkerOutput(process.stdout, process.stderr, process.returncode)
