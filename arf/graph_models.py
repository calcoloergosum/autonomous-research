"""Data-only internal graph requests and bounded read limits."""

from dataclasses import dataclass
from typing import Literal

from arf.graph_store import GraphError

Role = Literal['O', 'Q', 'H', 'C', 'T', 'R', 'E', 'B']


@dataclass(frozen=True)
class Ref:
    role: Role
    id: str
    revision: str | None = None


@dataclass(frozen=True)
class Actor:
    name: str
    role: Literal['recorder', 'operator']
    source: str


@dataclass(frozen=True)
class QueryLimits:
    depth: int = 8
    nodes: int = 128
    edges: int = 256
    output_bytes: int = 262144

    def validate(self) -> None:
        for name, low, high in (('depth', 0, 32), ('nodes', 1, 1024),
                                ('edges', 1, 2048), ('output_bytes', 1024, 1048576)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise GraphError('limit', f'{name} must be between {low} and {high}')
