from __future__ import annotations

from pathlib import Path

from match_my_contacts.race_results.models import RaceDataset, RaceResultRow
from match_my_contacts.race_results.storage import RaceResultsRepository


def make_dataset() -> RaceDataset:
    return RaceDataset(
        provider="acn_timing",
        source_url="https://example.test/#/events/1/ctx/db/generic/path/home/LIVE1",
        external_event_id="1",
        context_db="db",
        report_key="LIVE1",
        report_path="path",
        event_title="Demo Race",
        event_date="12/04/2026",
        event_location="Liege",
        event_country="BEL",
        total_results=2,
        metadata={"settings": {"Live": True}},
    )


def make_results() -> list[RaceResultRow]:
    return [
        RaceResultRow(
            group_name=None,
            group_rank=1,
            position_text="1.",
            bib="101",
            athlete_name="Alice Runner",
            team="Club A",
            country="BEL",
            finish_time="0:40:00",
            category="SEF",
            raw_row=["1.", "101", "Alice Runner"],
        ),
        RaceResultRow(
            group_name=None,
            group_rank=1,
            position_text="2.",
            bib="102",
            athlete_name="Bob Runner",
            team="Club B",
            country="BEL",
            finish_time="0:41:00",
            category="SEH",
            raw_row=["2.", "102", "Bob Runner"],
        ),
    ]


def test_save_dataset_replaces_existing_rows(tmp_path: Path) -> None:
    repository = RaceResultsRepository(tmp_path / "race_results.sqlite3")
    repository.initialize()

    dataset_id = repository.save_dataset(dataset=make_dataset(), results=make_results())
    dataset_id_again = repository.save_dataset(dataset=make_dataset(), results=make_results()[:1])

    datasets = repository.list_datasets()
    results = repository.list_results(dataset_id=dataset_id, limit=None)

    assert dataset_id == dataset_id_again
    assert len(datasets) == 1
    assert len(results) == 1
    assert results[0]["athlete_name"] == "Alice Runner"


def test_export_dataset_returns_metadata_and_results(tmp_path: Path) -> None:
    repository = RaceResultsRepository(tmp_path / "race_results.sqlite3")
    repository.initialize()

    dataset_id = repository.save_dataset(dataset=make_dataset(), results=make_results())
    payload = repository.export_dataset(dataset_id=dataset_id)

    assert payload["event_title"] == "Demo Race"
    assert payload["metadata"]["settings"]["Live"] is True
    assert payload["results"][0]["athlete_name"] == "Alice Runner"


def test_match_reviews_can_be_stored_and_cleared(tmp_path: Path) -> None:
    repository = RaceResultsRepository(tmp_path / "race_results.sqlite3")
    repository.initialize()

    dataset_id = repository.save_dataset(dataset=make_dataset(), results=make_results())
    result_id = repository.list_results(dataset_id=dataset_id, limit=1)[0]["id"]

    repository.set_match_review(
        dataset_id=dataset_id,
        result_id=result_id,
        status="accepted",
        contact_id=12,
        note="manual",
    )
    reviews = repository.list_match_reviews(dataset_id=dataset_id)

    assert reviews[0]["status"] == "accepted"
    assert reviews[0]["contact_id"] == 12
    assert repository.clear_match_review(dataset_id=dataset_id, result_id=result_id) is True


def test_clear_all_match_reviews_resets_table(tmp_path: Path) -> None:
    repository = RaceResultsRepository(tmp_path / "race_results.sqlite3")
    repository.initialize()

    dataset_id = repository.save_dataset(dataset=make_dataset(), results=make_results())
    result_id = repository.list_results(dataset_id=dataset_id, limit=1)[0]["id"]
    repository.set_match_review(
        dataset_id=dataset_id,
        result_id=result_id,
        status="accepted",
        contact_id=12,
        note="manual",
    )

    deleted_count = repository.clear_all_match_reviews()

    assert deleted_count == 1
    assert repository.list_match_reviews(dataset_id=dataset_id) == []


def test_dataset_aliases_can_be_added_and_resolved(tmp_path: Path) -> None:
    repository = RaceResultsRepository(tmp_path / "race_results.sqlite3")
    repository.initialize()

    dataset_id = repository.save_dataset(dataset=make_dataset(), results=make_results())
    repository.add_dataset_alias(dataset_id=dataset_id, alias_text="demo-race")

    datasets = repository.list_datasets()
    aliases = repository.list_dataset_aliases(dataset_id=dataset_id)

    assert datasets[0]["aliases"] == ["demo-race"]
    assert aliases[0]["alias_text"] == "demo-race"
    assert repository.resolve_dataset_selector("demo-race") == dataset_id
    assert repository.remove_dataset_alias(alias_text="demo-race") is True
