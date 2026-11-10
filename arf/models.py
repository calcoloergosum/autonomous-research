"""Validation of imported proposals and worker observations."""

from dataclasses import dataclass
import json
import math
from typing import Any

import yaml


class ARFError(Exception):
    """An actionable input, state, or execution error."""


def json_text(value: Any) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ARFError(f"{name} must be a nonempty string")
    return value


def string_list(value: Any, name: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise ARFError(f"{name} must be {'a nonempty' if required else 'a'} list")
    return [nonempty_string(item, name) for item in value]


def finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"values"}:
        raise ARFError("demo_mean input must contain only values")
    values = value["values"]
    if not isinstance(values, list) or not values or not all(map(finite_number, values)):
        raise ARFError("input.values must be a nonempty finite number list (no bool)")
    return value


def validate_result(value: Any, count: int) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"mean", "count"}:
        raise ARFError("worker result must contain only mean and count")
    if not finite_number(value["mean"]):
        raise ARFError("worker mean must be finite")
    if type(value["count"]) is not int or value["count"] != count:
        raise ARFError("worker count does not match input")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ARFError(f"duplicate field: {key}")
        result[key] = value
    return result


def parse_json(data: str | bytes) -> Any:
    try:
        return json.loads(data, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ARFError("invalid JSON") from exc


class _UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML with duplicate keys rejected instead of silently overwritten."""


def _yaml_mapping(loader: _UniqueSafeLoader, node: yaml.MappingNode) -> dict:
    pairs = []
    for key, value in node.value:
        field = loader.construct_object(key, deep=True)
        if not isinstance(field, str):
            raise ARFError("charter keys must be strings")
        pairs.append((field, loader.construct_object(value, deep=True)))
    return _unique_object(pairs)


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping
)


@dataclass(frozen=True)
class Charter:
    study_id: str
    question: str
    success_criteria: list[str]
    constraints: list[str]
    source: bytes

    @classmethod
    def parse(cls, source: bytes) -> "Charter":
        try:
            data = yaml.load(source, Loader=_UniqueSafeLoader)
        except (yaml.YAMLError, UnicodeError, RecursionError) as exc:
            raise ARFError("invalid charter YAML") from exc
        if not isinstance(data, dict):
            raise ARFError("charter must be a YAML mapping")
        return cls(
            nonempty_string(data.get("study_id"), "study_id"),
            nonempty_string(data.get("question"), "question"),
            string_list(data.get("success_criteria"), "success_criteria", required=True),
            string_list(data.get("constraints", []), "constraints"),
            source,
        )


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    study_id: str
    title: str
    description: str
    kind: str
    input: dict[str, Any]
    dependencies: list[str]

    @classmethod
    def parse(cls, data: Any) -> "TaskSpec":
        fields = {"task_id", "study_id", "title", "description", "kind", "input", "dependencies"}
        required = fields - {"description", "dependencies"}
        if not isinstance(data, dict) or set(data) - fields or required - set(data):
            raise ARFError("task spec has missing or unsupported fields")
        if data["kind"] != "demo_mean":
            raise ARFError("only kind=demo_mean is supported")
        description = data.get("description", "")
        if not isinstance(description, str):
            raise ARFError("description must be a string")
        dependencies = string_list(data.get("dependencies", []), "dependencies")
        if len(set(dependencies)) != len(dependencies):
            raise ARFError("duplicate dependencies")
        return cls(
            nonempty_string(data["task_id"], "task_id"),
            nonempty_string(data["study_id"], "study_id"),
            nonempty_string(data["title"], "title"),
            description,
            data["kind"],
            validate_input(data["input"]),
            dependencies,
        )


def check_acyclic(graph: dict[str, list[str]]) -> None:
    """Iterative DFS also handles long prerequisite chains."""
    done: set[str] = set()
    active: set[str] = set()
    for root in graph:
        stack = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.remove(node)
                done.add(node)
                continue
            if node in active:
                raise ARFError("dependency cycle")
            if node in done:
                continue
            active.add(node)
            stack.append((node, True))
            stack.extend((dep, False) for dep in graph.get(node, []))
