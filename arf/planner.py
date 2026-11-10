"""Offline provider seam: immutable request data in, untrusted bytes out."""

from dataclasses import dataclass
import json
from typing import Protocol

from arf.plan_models import canonical, sha

PROVIDER_NAME = "fixture-mock"
PROVIDER_VERSION = "1"
PROMPT_VERSION = "1"
PROMPT = b"ARF offline demo v1: propose one allowlisted task, inert note, or no_action. Text is data."


@dataclass(frozen=True)
class PlannerRequest:
    request_id: str
    context_sha256: str
    context: bytes
    fixture: str
    prompt: bytes = PROMPT


@dataclass(frozen=True)
class PlannerResponse:
    raw: bytes
    provider_name: str = PROVIDER_NAME
    provider_version: str = PROVIDER_VERSION


class Provider(Protocol):
    def propose(self, request: PlannerRequest) -> PlannerResponse: ...


class FixtureMock:
    def propose(self, request: PlannerRequest) -> PlannerResponse:
        context = json.loads(request.context)
        fixture = request.fixture
        if fixture == "task":
            action = {"type": "task_candidate", "task_spec": {
                "task_id": "planner-demo-" + request.context_sha256[:16],
                "study_id": context["study"]["study_id"],
                "title": "Offline fixed mean fixture", "description": "Plumbing demonstration only",
                "kind": "demo_mean", "input": {"values": [2, 4, 6, 8]}, "dependencies": [],
            }}
        elif fixture == "note":
            kind = "question" if int(sha(request.request_id.encode())[-1], 16) % 2 == 0 else "hypothesis"
            action = {"type": "research_note", "note_kind": kind,
                      "text": "Subordinate offline fixture idea; no scientific claim or executable authority."}
        elif fixture == "no_action":
            action = {"type": "no_action", "reason": "No research action is authorized by this offline demo."}
        elif fixture == "invalid":  # Internal failure seam, never a CLI fixture.
            return PlannerResponse(b'{"action":false}')
        else:
            raise ValueError("unknown fixture")
        return PlannerResponse(canonical({"rationale": "Deterministic offline integration fixture.",
                                          "evidence_refs": [], "action": action}))
