from __future__ import annotations

from pathlib import Path

from running_contacts.contacts.models import ContactMethod, ContactRecord
from running_contacts.contacts.storage import ContactsRepository
from running_contacts.matching.service import match_dataset
from running_contacts.race_results.models import RaceDataset, RaceResultRow
from running_contacts.race_results.storage import RaceResultsRepository


def _seed_contacts(db_path: Path) -> None:
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Jean-Francois Dupont",
                given_name="Jean-Francois",
                family_name="Dupont",
                methods=[
                    ContactMethod(
                        kind="email",
                        value="jf.dupont@example.com",
                        normalized_value="jf.dupont@example.com",
                    )
                ],
                raw_payload={"resourceName": "people/1"},
            ),
            ContactRecord(
                source_contact_id="people/2",
                display_name="Alice Martin",
                given_name="Alice",
                family_name="Martin",
                raw_payload={"resourceName": "people/2"},
            ),
        ],
        sync_run_id=sync_run_id,
    )


def _seed_results(db_path: Path) -> int:
    repository = RaceResultsRepository(db_path)
    repository.initialize()
    return repository.save_dataset(
        dataset=RaceDataset(
            provider="acn_timing",
            source_url="https://example.test",
            external_event_id="1",
            context_db="demo",
            report_key="LIVE1",
            report_path="197994_1",
            event_title="Demo Race",
            event_date="12/04/2026",
            event_location="Liege",
            event_country="BEL",
            total_results=3,
            metadata={},
        ),
        results=[
            RaceResultRow(
                group_name=None,
                group_rank=1,
                position_text="1.",
                bib="101",
                athlete_name="Jean Francois DUPONT",
                finish_time="0:40:00",
                raw_row=[],
            ),
            RaceResultRow(
                group_name=None,
                group_rank=1,
                position_text="2.",
                bib="102",
                athlete_name="Alice Marten",
                finish_time="0:41:00",
                raw_row=[],
            ),
            RaceResultRow(
                group_name=None,
                group_rank=1,
                position_text="3.",
                bib="103",
                athlete_name="Unknown Runner",
                finish_time="0:42:00",
                raw_row=[],
            ),
        ],
    )


def test_match_dataset_accepts_exact_and_fuzzy_matches(tmp_path: Path) -> None:
    contacts_db_path = tmp_path / "contacts.sqlite3"
    results_db_path = tmp_path / "race_results.sqlite3"
    _seed_contacts(contacts_db_path)
    dataset_id = _seed_results(results_db_path)

    report = match_dataset(
        contacts_db_path=contacts_db_path,
        results_db_path=results_db_path,
        dataset_id=dataset_id,
        min_score=85.0,
        min_gap=3.0,
    )

    assert report.contacts_count == 2
    assert report.results_count == 3
    assert len(report.accepted_matches) == 2
    assert report.accepted_matches[0].contact_name == "Jean-Francois Dupont"
    assert report.accepted_matches[0].match_method == "exact"
    assert report.accepted_matches[1].contact_name == "Alice Martin"
    assert report.accepted_matches[1].match_method == "fuzzy"
    assert report.unmatched_count == 1


def test_match_dataset_marks_close_scores_as_ambiguous(tmp_path: Path) -> None:
    contacts_db_path = tmp_path / "contacts.sqlite3"
    results_db_path = tmp_path / "race_results.sqlite3"

    repository = ContactsRepository(contacts_db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/0",
                display_name="Jean-Francois Dupont",
                given_name="Jean-Francois",
                family_name="Dupont",
                raw_payload={"resourceName": "people/0"},
            ),
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Martin",
                given_name="Alice",
                family_name="Martin",
                raw_payload={"resourceName": "people/1"},
            ),
            ContactRecord(
                source_contact_id="people/2",
                display_name="Alice Martens",
                given_name="Alice",
                family_name="Martens",
                raw_payload={"resourceName": "people/2"},
            ),
        ],
        sync_run_id=sync_run_id,
    )
    dataset_id = _seed_results(results_db_path)

    report = match_dataset(
        contacts_db_path=contacts_db_path,
        results_db_path=results_db_path,
        dataset_id=dataset_id,
        min_score=85.0,
        min_gap=5.0,
    )

    assert len(report.accepted_matches) == 1
    assert len(report.ambiguous_matches) == 1
    assert report.ambiguous_matches[0].athlete_name == "Alice Marten"


def test_match_dataset_applies_aliases_and_reviews(tmp_path: Path) -> None:
    contacts_db_path = tmp_path / "contacts.sqlite3"
    results_db_path = tmp_path / "race_results.sqlite3"
    _seed_contacts(contacts_db_path)
    dataset_id = _seed_results(results_db_path)

    contacts_repository = ContactsRepository(contacts_db_path)
    contacts_repository.initialize()
    contacts_repository.add_alias(contact_id=2, alias_text="Alice Marten")

    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    unknown_result = results_repository.list_results(dataset_id=dataset_id, query="Unknown", limit=1)[0]
    results_repository.set_match_review(
        dataset_id=dataset_id,
        result_id=unknown_result["id"],
        status="rejected",
        note="not in contacts",
    )

    report = match_dataset(
        contacts_db_path=contacts_db_path,
        results_db_path=results_db_path,
        dataset_id=dataset_id,
    )

    assert any(match.athlete_name == "Alice Marten" and match.match_method == "exact" for match in report.accepted_matches)
    assert report.reviewed_rejections_count == 1
