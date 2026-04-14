from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from running_contacts.matching.models import MatchReport


@dataclass(slots=True)
class MatchingFilters:
    status: str = "accepted"
    sort_by: str = "position"
    team: str | None = None
    name_query: str | None = None
    category: str | None = None
    reviewed_only: bool = False


@dataclass(slots=True)
class GuiState:
    current_dataset_selector: str | None = None
    last_dataset_id: int | None = None
    last_match_report: MatchReport | None = None
    current_matching_filters: MatchingFilters = field(default_factory=MatchingFilters)
    last_export_path: Path | None = None
