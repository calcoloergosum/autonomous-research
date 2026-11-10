"""Data-only versioned offline decision inputs. Text never selects execution."""
from dataclasses import dataclass, field
from typing import Literal

from arf.graph_models import QueryLimits, Ref
from arf.plan_models import PlanError, canonical, strict_json


@dataclass(frozen=True)
class Selection:
    roles: tuple[str, ...] = ()
    edge_types: tuple[str, ...] = ()
    node: Ref | None = None
    limits: QueryLimits = field(default_factory=QueryLimits)
    omissions: str = 'Only the declared bounded graph view; portfolio remains partial.'


@dataclass(frozen=True)
class Impact:
    status: Literal['qualitative', 'unknown', 'incomparable', 'contested'] = 'unknown'
    rationale: str = 'Synthetic plumbing cannot establish scientific importance.'
    assumptions: str = 'Fictional fixture; human study criteria remain external.'
    uncertainty: str = 'Uncalibrated; scientific importance unknown.'
    alternatives: str = 'Other interpretations and priorities may be preferable.'


@dataclass(frozen=True)
class Costs:
    wall_seconds: float | None = 1.0
    cpu_seconds: float | None = None
    gpu_seconds: float | None = 0
    llm_tokens: int | None = 0
    human_minutes: float | None = 0
    money: float | None = None
    currency: str | None = None
    synthetic_tokens: int | None = 1


@dataclass(frozen=True)
class Synthetic:
    viable: int = 0
    nonviable: int = 0
    information_bonus: int = 0
    branch_relevant: bool = False
    costs: Costs = field(default_factory=Costs)


@dataclass(frozen=True)
class CandidateDefinition:
    origin_key: str
    description: str
    intended_result: str = 'Fictional decision-loop exercise.'
    origin_kind: str = 'synthetic_fixture'
    origin_sha256: str = '0' * 64
    version: int = 1
    previous: int | None = None
    kind: Literal['explore', 'experiment', 'replicate', 'synthesize'] = 'experiment'
    origin_order: int = 0
    refs: tuple[Ref, ...] = ()
    impact: Impact = field(default_factory=Impact)
    synthetic: Synthetic | None = None


@dataclass(frozen=True)
class Rule:
    task_id: str
    spec_sha256: str
    effect: Literal['engineering_only', 'branch_from_mean']
    cost_surprise: int | None = None


@dataclass(frozen=True)
class Feedback:
    source: str = 'offline-synthetic-scenario-v1'
    branch: Literal['unknown', 'viable', 'nonviable'] = 'unknown'
    evidence_refs: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = ()
    cost_overrides: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Policy:
    name: Literal['static', 'information'] = 'information'
    version: int = 1
    weight: int = 1


@dataclass(frozen=True)
class Constraints:
    ceilings: dict[str, float] = field(default_factory=lambda: {'synthetic_tokens': 10})
    hard: tuple[str, ...] = ()
    currency: str | None = None


def bounded(value, limit=65536) -> bytes:
    raw = canonical(value)
    if len(raw) > limit:
        raise PlanError('limit', f'decision payload exceeds {limit} bytes')
    # Reuse the bounded depth/text scanner without its 64 KiB response size cap.
    if limit <= 65536:
        strict_json(raw)
    else:
        from arf.plan_models import _scan_depth, text
        _scan_depth(raw)
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                text(item, 'decision text', empty=True)
            elif isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, (list, tuple)):
                pending.extend(item)
    return raw
