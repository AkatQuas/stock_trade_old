"""Candidate dataclasses for quantitative preselect."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Candidate:
    code: str
    date: str
    strategy: str
    close: float
    turnover_n: float
    brick_growth: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["extra"]:
            d.pop("extra")
        if d["brick_growth"] is None:
            d.pop("brick_growth")
        return d


@dataclass
class CandidateRun:
    run_date: str
    pick_date: str
    candidates: list[Candidate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_date": self.run_date,
            "pick_date": self.pick_date,
            "candidates": [c.to_dict() for c in self.candidates],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CandidateRun:
        candidates = [
            Candidate(**{k: v for k, v in c.items() if k in Candidate.__dataclass_fields__})
            for c in d.get("candidates", [])
        ]
        return cls(
            run_date=d["run_date"],
            pick_date=d["pick_date"],
            candidates=candidates,
            meta=d.get("meta", {}),
        )
