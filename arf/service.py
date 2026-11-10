"""Controller locking and the claim -> execute -> finalize lifecycle."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import fcntl
from pathlib import Path
import time

from arf.executor import OUTPUT_LIMIT, WorkerOutput, execute_demo
from arf.models import ARFError, parse_json, validate_input, validate_result
from arf.store import Store


@contextmanager
def controller_lock(database: Path) -> Iterator[None]:
    # Persistent inode: unlinking lock files would allow simultaneous lock owners.
    with Path(str(database.resolve()) + ".controller.lock").open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ARFError("controller busy: run-next or recover is already active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def bounded_text(text: str) -> str:
    # Retain printable error/output text, bounded for inspection.
    return "".join(c for c in text[:OUTPUT_LIMIT] if c.isprintable() or c in "\n\t")


def run_next(store: Store, executor: Callable[[dict], WorkerOutput] = execute_demo) -> dict:
    with controller_lock(store.path):
        claim = store.claim_next()
        if claim is None:
            return {"status": "no_ready_task"}
        task = claim["task"]
        start = time.monotonic()
        result = None
        error = None
        exit_code = None
        stdout = stderr = ""
        try:
            # Recheck the persisted allowlist before execution as well as at import.
            if task["kind"] != "demo_mean":
                raise ARFError("unsupported stored task kind")
            validate_input(task["input"])
            output = executor(task["input"])
            exit_code = output.exit_code
            stdout = bounded_text(output.stdout)
            stderr = bounded_text(output.stderr)
            if len(output.stdout) > OUTPUT_LIMIT or len(output.stderr) > OUTPUT_LIMIT:
                raise ARFError("worker output exceeds limit")
            if exit_code != 0:
                raise ARFError(f"demo worker exited with code {exit_code}")
            result = validate_result(parse_json(output.stdout), len(task["input"]["values"]))
        except Exception as exc:
            # Never turn a controller interruption (BaseException) into a completed run.
            error = bounded_text(str(exc)) if isinstance(exc, ARFError) else f"executor error: {type(exc).__name__}"
        elapsed = time.monotonic() - start
        # If finalization itself fails, retain the running attempt for explicit recovery.
        run = store.finish_run(
            claim["run_id"], result=result, error=error, exit_code=exit_code,
            stdout=stdout, stderr=stderr, wall_seconds=elapsed,
        )
        return {"status": run["status"], "task_id": task["task_id"], "run": run}


def recover(store: Store) -> dict:
    with controller_lock(store.path):
        return {"status": "recovered", "interrupted": store.recover()}
