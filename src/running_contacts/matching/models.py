from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MatchResult:
    status: str
    match_method: str
    score: float
    matched_alias: str | None
    confidence_gap: float
    result_id: int
    dataset_id: int
    athlete_name: str
    position_text: str | None
    bib: str | None
    finish_time: str | None
    team: str | None
    category: str | None
    contact_id: int | None = None
    contact_name: str | None = None


@dataclass(slots=True)
class MatchReport:
    dataset: dict
    accepted_matches: list[MatchResult] = field(default_factory=list)
    ambiguous_matches: list[MatchResult] = field(default_factory=list)
    unmatched_count: int = 0
    reviewed_rejections_count: int = 0
    contacts_count: int = 0
    results_count: int = 0
