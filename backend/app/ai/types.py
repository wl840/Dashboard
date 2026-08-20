from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlannedTool:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class PlanningResult:
    plan: PlannedTool | None
    provider: str
    fallback_reason: str | None = None
