"""Bounded, strict untrusted response validation; no storage or execution authority."""

from dataclasses import asdict
import hashlib
import json
from typing import Any

from arf.models import ARFError, TaskSpec, parse_json

CONTEXT_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 64 * 1024
TEXT_LIMIT = 4 * 1024
LIST_LIMIT = 64
DEPTH_LIMIT = 32
CANONICAL_VERSION = 1
EXPORT_VERSION = 1


class PlanError(ARFError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlanError("invalid", "cannot canonicalize JSON") from exc


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text(value: Any, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise PlanError("invalid", f"{name} must be nonempty text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise PlanError("invalid", f"{name} must be UTF-8") from exc
    if size > TEXT_LIMIT:
        raise PlanError("limit", f"{name} exceeds 4 KiB")
    return value


def hash_text(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise PlanError("invalid", "expected lowercase SHA-256")
    return value


def fields(value: Any, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise PlanError("invalid", "missing or unsupported fields")


def _scan_depth(raw: bytes) -> None:
    # Scan delimiters before JSON parsing. Delimiters inside strings are data.
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > DEPTH_LIMIT:
                raise PlanError("limit", "JSON nesting exceeds 32 containers")
        elif char in (93, 125):
            depth -= 1


def strict_json(raw: bytes) -> Any:
    if not isinstance(raw, bytes):
        raise PlanError("invalid", "provider response must be bytes")
    if len(raw) > RESPONSE_LIMIT:
        raise PlanError("limit", "provider response exceeds 64 KiB")
    _scan_depth(raw)
    try:
        data = parse_json(raw.decode("utf-8"))
    except (ARFError, UnicodeError) as exc:
        raise PlanError("invalid", "invalid JSON or duplicate keys") from exc
    # Check every field, including otherwise ignored/unknown fields, for bounds
    # and nonfinite constants before schema validation.
    pending = [data]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            text(item, "response text", empty=True)
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, float):
            import math
            if not math.isfinite(item):
                raise PlanError("invalid", "nonfinite JSON number")
    return data


def normalize_response(raw: bytes, context: dict) -> dict:
    data = strict_json(raw)
    fields(data, {"rationale", "evidence_refs", "action"})
    text(data["rationale"], "rationale")
    refs = data["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > LIST_LIMIT:
        raise PlanError("limit", "evidence_refs must be a list of at most 64 IDs")
    for ref in refs:
        text(ref, "evidence reference")
    if len(set(refs)) != len(refs) or not set(refs) <= {e["evidence_id"] for e in context["evidence"]}:
        raise PlanError("invalid", "duplicate or unknown evidence references")
    action = data["action"]
    if not isinstance(action, dict):
        raise PlanError("invalid", "action must be a tagged object")
    kind = action.get("type")
    if kind == "task_candidate":
        fields(action, {"type", "task_spec"})
        try:
            spec = TaskSpec.parse(action["task_spec"])
        except ARFError as exc:
            raise PlanError("invalid", "invalid allowlisted TaskSpec") from exc
        if len(spec.dependencies) > LIST_LIMIT:
            raise PlanError("limit", "dependencies exceed 64")
        if spec.study_id != context["study"]["study_id"]:
            raise PlanError("invalid", "task study does not match context")
        existing = {task["task_id"] for task in context["tasks"]}
        if spec.task_id in spec.dependencies or not set(spec.dependencies) <= existing:
            raise PlanError("invalid", "dependencies must already exist in the pinned study")
        normalized = asdict(spec)
        normalized["dependencies"] = sorted(spec.dependencies)
        action = {"type": kind, "task_spec": normalized}
    elif kind == "research_note":
        fields(action, {"type", "note_kind", "text"})
        if action["note_kind"] not in ("question", "hypothesis"):
            raise PlanError("invalid", "unsupported note kind")
        text(action["text"], "note text")
    elif kind == "no_action":
        fields(action, {"type", "reason"})
        text(action["reason"], "reason")
    else:
        raise PlanError("invalid", "unsupported action type")
    return {"rationale": data["rationale"], "evidence_refs": sorted(refs), "action": action}


def proposal_content(response: dict, context: dict, context_hash: str) -> dict:
    return {"proposal_version": 1, "study_id": context["study"]["study_id"],
            "charter_sha256": context["study"]["source_sha256"],
            "context_sha256": context_hash, **response}


def action_hash(content: dict) -> str | None:
    action = content["action"]
    if action["type"] != "task_candidate":
        return None
    return sha(canonical({"study_id": content["study_id"], "task_spec": action["task_spec"]}))
