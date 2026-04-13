from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from running_contacts.contacts.storage import ContactsRepository
from running_contacts.race_results.storage import RaceResultsRepository

from .models import MatchReport, MatchResult
from .normalization import normalize_person_name, normalize_person_name_tokens


@dataclass(slots=True)
class _AliasEntry:
    contact_id: int
    contact_name: str
    alias_text: str
    normalized_alias: str
    token_alias: str
    tokens: tuple[str, ...]
    first_token: str
    last_token: str
    strong_tokens: frozenset[str]
    given_tokens: tuple[str, ...]
    family_tokens: tuple[str, ...]


class _MatcherIndex:
    def __init__(self, contacts: list[dict]) -> None:
        self.contacts_count = len(contacts)
        self._aliases: dict[str, _AliasEntry] = {}
        self._exact: dict[str, list[_AliasEntry]] = {}
        self._exact_token: dict[str, list[_AliasEntry]] = {}
        self._by_first_token: dict[str, list[_AliasEntry]] = {}
        self._by_last_token: dict[str, list[_AliasEntry]] = {}
        self._by_strong_token: dict[str, list[_AliasEntry]] = {}

        for contact in contacts:
            for alias_text in _build_contact_aliases(contact):
                normalized_alias = normalize_person_name(alias_text)
                token_alias = normalize_person_name_tokens(alias_text)
                tokens = tuple(normalized_alias.split())
                if not normalized_alias:
                    continue

                alias_key = f"{contact['id']}::{normalized_alias}"
                if alias_key in self._aliases:
                    continue

                first_token = tokens[0]
                last_token = tokens[-1]
                strong_tokens = frozenset(token for token in tokens if len(token) >= 4)
                given_tokens = tuple(normalize_person_name(contact.get("given_name")).split())
                family_tokens = tuple(normalize_person_name(contact.get("family_name")).split())
                entry = _AliasEntry(
                    contact_id=int(contact["id"]),
                    contact_name=str(contact["display_name"]),
                    alias_text=alias_text,
                    normalized_alias=normalized_alias,
                    token_alias=token_alias,
                    tokens=tokens,
                    first_token=first_token,
                    last_token=last_token,
                    strong_tokens=strong_tokens,
                    given_tokens=given_tokens,
                    family_tokens=family_tokens,
                )
                self._aliases[alias_key] = entry
                self._exact.setdefault(normalized_alias, []).append(entry)
                if token_alias:
                    self._exact_token.setdefault(token_alias, []).append(entry)
                self._by_first_token.setdefault(first_token, []).append(entry)
                self._by_last_token.setdefault(last_token, []).append(entry)
                for token in strong_tokens:
                    self._by_strong_token.setdefault(token, []).append(entry)

    def match_name(self, result: dict, *, min_score: float, min_gap: float) -> MatchResult | None:
        athlete_name = str(result["athlete_name"])
        normalized_name = normalize_person_name(athlete_name)
        token_name = normalize_person_name_tokens(athlete_name)
        query_tokens = tuple(normalized_name.split())
        if not normalized_name:
            return None

        exact_candidates = self._distinct_contacts(
            self._exact.get(normalized_name, []) + self._exact_token.get(token_name, [])
        )
        if len(exact_candidates) == 1:
            entry = exact_candidates[0]
            return _build_match_result(
                result=result,
                entry=entry,
                status="accepted",
                match_method="exact",
                score=100.0,
                confidence_gap=100.0,
            )
        if len(exact_candidates) > 1:
            return MatchResult(
                status="ambiguous",
                match_method="exact",
                score=100.0,
                matched_alias=None,
                confidence_gap=0.0,
                result_id=int(result["id"]),
                dataset_id=int(result["dataset_id"]),
                athlete_name=athlete_name,
                position_text=result.get("position_text"),
                bib=result.get("bib"),
                finish_time=result.get("finish_time"),
                team=result.get("team"),
                category=result.get("category"),
            )

        candidate_entries = self._candidate_entries(query_tokens)
        if not candidate_entries:
            return None

        extracted = process.extract(
            normalized_name,
            {key: entry.normalized_alias for key, entry in candidate_entries.items()},
            scorer=fuzz.WRatio,
            processor=None,
            limit=8,
        )

        scored_candidates: list[tuple[_AliasEntry, float]] = []
        seen_contacts: set[int] = set()
        for _, score, alias_key in extracted:
            entry = candidate_entries[alias_key]
            if entry.contact_id in seen_contacts:
                continue
            seen_contacts.add(entry.contact_id)
            if not _is_plausible_fuzzy_candidate(query_tokens, entry):
                continue
            adjusted_score = max(
                float(score),
                float(fuzz.ratio(normalized_name, entry.normalized_alias)),
            )
            scored_candidates.append((entry, adjusted_score))

        if not scored_candidates:
            return None

        best_entry, best_score = scored_candidates[0]
        second_score = scored_candidates[1][1] if len(scored_candidates) > 1 else 0.0
        confidence_gap = best_score - second_score
        if best_score >= min_score and confidence_gap >= min_gap:
            return _build_match_result(
                result=result,
                entry=best_entry,
                status="accepted",
                match_method="fuzzy",
                score=best_score,
                confidence_gap=confidence_gap,
            )
        if best_score >= min_score:
            return _build_match_result(
                result=result,
                entry=best_entry,
                status="ambiguous",
                match_method="fuzzy",
                score=best_score,
                confidence_gap=confidence_gap,
            )
        return None

    @staticmethod
    def _distinct_contacts(entries: list[_AliasEntry]) -> list[_AliasEntry]:
        distinct: list[_AliasEntry] = []
        seen_contact_ids: set[int] = set()
        for entry in entries:
            if entry.contact_id in seen_contact_ids:
                continue
            seen_contact_ids.add(entry.contact_id)
            distinct.append(entry)
        return distinct

    def _candidate_entries(self, query_tokens: tuple[str, ...]) -> dict[str, _AliasEntry]:
        if len(query_tokens) < 2:
            return {}

        candidates: dict[str, _AliasEntry] = {}
        first_token = query_tokens[0]
        last_token = query_tokens[-1]
        strong_tokens = [token for token in query_tokens if len(token) >= 4]

        for entry in self._by_first_token.get(first_token, []):
            candidates[f"{entry.contact_id}::{entry.normalized_alias}"] = entry
        for entry in self._by_last_token.get(last_token, []):
            candidates[f"{entry.contact_id}::{entry.normalized_alias}"] = entry
        for token in strong_tokens:
            for entry in self._by_strong_token.get(token, []):
                candidates[f"{entry.contact_id}::{entry.normalized_alias}"] = entry

        return candidates


def match_dataset(
    *,
    contacts_db_path: Path,
    results_db_path: Path,
    dataset_id: int,
    include_inactive_contacts: bool = False,
    min_score: float = 95.0,
    min_gap: float = 3.0,
) -> MatchReport:
    contacts_repository = ContactsRepository(contacts_db_path)
    contacts_repository.initialize()
    contacts = contacts_repository.list_contacts(include_inactive=include_inactive_contacts)

    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    dataset = results_repository.get_dataset(dataset_id=dataset_id)
    results = results_repository.list_results(dataset_id=dataset_id, limit=None)
    reviews_by_result_id = results_repository.get_match_reviews_map(dataset_id=dataset_id)

    matcher = _MatcherIndex(contacts)
    contacts_by_id = {int(contact["id"]): contact for contact in contacts}
    accepted_matches: list[MatchResult] = []
    ambiguous_matches: list[MatchResult] = []
    unmatched_count = 0
    reviewed_rejections_count = 0

    for result in results:
        review = reviews_by_result_id.get(int(result["id"]))
        if review:
            if review["status"] == "accepted":
                contact = contacts_by_id.get(int(review["contact_id"]))
                if contact is not None:
                    accepted_matches.append(
                        MatchResult(
                            status="accepted",
                            match_method="review",
                            score=100.0,
                            matched_alias=None,
                            confidence_gap=100.0,
                            result_id=int(result["id"]),
                            dataset_id=int(result["dataset_id"]),
                            athlete_name=str(result["athlete_name"]),
                            position_text=result.get("position_text"),
                            bib=result.get("bib"),
                            finish_time=result.get("finish_time"),
                            team=result.get("team"),
                            category=result.get("category"),
                            contact_id=int(contact["id"]),
                            contact_name=str(contact["display_name"]),
                        )
                    )
                    continue
            elif review["status"] == "rejected":
                unmatched_count += 1
                reviewed_rejections_count += 1
                continue

        match = matcher.match_name(result, min_score=min_score, min_gap=min_gap)
        if match is None:
            unmatched_count += 1
        elif match.status == "accepted":
            accepted_matches.append(match)
        else:
            ambiguous_matches.append(match)

    accepted_matches.sort(key=lambda item: (item.position_text or "999999", item.athlete_name))
    ambiguous_matches.sort(key=lambda item: (-item.score, item.athlete_name))

    return MatchReport(
        dataset=dataset,
        accepted_matches=accepted_matches,
        ambiguous_matches=ambiguous_matches,
        unmatched_count=unmatched_count,
        reviewed_rejections_count=reviewed_rejections_count,
        contacts_count=matcher.contacts_count,
        results_count=len(results),
    )


def export_matches_csv(*, report: MatchReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "dataset_id",
                "athlete_name",
                "contact_name",
                "match_method",
                "score",
                "position_text",
                "finish_time",
                "team",
                "category",
                "bib",
                "matched_alias",
            ],
        )
        writer.writeheader()
        for match in report.accepted_matches:
            writer.writerow(
                {
                    "dataset_id": match.dataset_id,
                    "athlete_name": match.athlete_name,
                    "contact_name": match.contact_name,
                    "match_method": match.match_method,
                    "score": f"{match.score:.1f}",
                    "position_text": match.position_text or "",
                    "finish_time": match.finish_time or "",
                    "team": match.team or "",
                    "category": match.category or "",
                    "bib": match.bib or "",
                    "matched_alias": match.matched_alias or "",
                }
            )
    return output_path


def _build_contact_aliases(contact: dict) -> list[str]:
    aliases: list[str] = []
    for value in (
        contact.get("display_name"),
        _join_name(contact.get("given_name"), contact.get("family_name")),
        _join_name(contact.get("family_name"), contact.get("given_name")),
        contact.get("nickname"),
        _join_name(contact.get("nickname"), contact.get("family_name")),
        *contact.get("aliases", []),
    ):
        if isinstance(value, str) and value.strip() and value.strip() not in aliases:
            aliases.append(value.strip())
    return aliases


def _join_name(left: str | None, right: str | None) -> str | None:
    parts = [part.strip() for part in [left, right] if isinstance(part, str) and part.strip()]
    return " ".join(parts) or None


def _build_match_result(
    *,
    result: dict,
    entry: _AliasEntry,
    status: str,
    match_method: str,
    score: float,
    confidence_gap: float,
) -> MatchResult:
    return MatchResult(
        status=status,
        match_method=match_method,
        score=score,
        matched_alias=entry.alias_text,
        confidence_gap=confidence_gap,
        result_id=int(result["id"]),
        dataset_id=int(result["dataset_id"]),
        athlete_name=str(result["athlete_name"]),
        position_text=result.get("position_text"),
        bib=result.get("bib"),
        finish_time=result.get("finish_time"),
        team=result.get("team"),
        category=result.get("category"),
        contact_id=entry.contact_id,
        contact_name=entry.contact_name,
    )


def _is_plausible_fuzzy_candidate(query_tokens: tuple[str, ...], entry: _AliasEntry) -> bool:
    if len(query_tokens) < 2 or len(entry.tokens) < 2:
        return False

    if entry.given_tokens and entry.family_tokens:
        family_similarity = max(
            float(fuzz.ratio(query_token, family_token))
            for query_token in query_tokens
            for family_token in entry.family_tokens
        )
        given_similarity = max(
            float(fuzz.ratio(query_token, given_token))
            for query_token in query_tokens
            for given_token in entry.given_tokens
        )
        return family_similarity >= 80.0 and given_similarity >= 85.0

    query_first = query_tokens[0]
    query_last = query_tokens[-1]
    shared_tokens = set(query_tokens) & set(entry.tokens)
    shared_strong_tokens = {token for token in shared_tokens if len(token) >= 4}
    first_similarity = float(fuzz.ratio(query_first, entry.first_token))
    last_similarity = float(fuzz.ratio(query_last, entry.last_token))

    return bool(
        len(shared_strong_tokens) >= 2
        or (query_first == entry.first_token and last_similarity >= 80.0)
        or (query_last == entry.last_token and first_similarity >= 80.0)
        or (len(shared_tokens) >= 1 and first_similarity >= 95.0 and last_similarity >= 80.0)
    )
