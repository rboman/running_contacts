from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from match_my_contacts.cli import app
from match_my_contacts.config import default_credentials_path, get_config_path
from match_my_contacts.contacts.models import ContactRecord, SyncStats
from match_my_contacts.contacts.storage import ContactsRepository
from match_my_contacts.matching.models import MatchReport, MatchResult
from match_my_contacts.race_results.models import RaceFetchStats
from match_my_contacts.race_results.storage import RaceResultsRepository


runner = CliRunner()


def test_hello_does_not_require_config_file() -> None:
    config_path = get_config_path()
    if config_path.exists():
        config_path.unlink()

    result = runner.invoke(app, ["hello"])

    assert result.exit_code == 0
    assert not config_path.exists()


def test_config_show_outputs_resolved_paths() -> None:
    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "config_path:" in result.stdout
    assert "data_dir:" in result.stdout
    assert "contacts_db:" in result.stdout
    assert "credentials_path:" in result.stdout


def test_contacts_list_uses_configured_default_data_dir() -> None:
    app_data_dir = Path.cwd() / "data"
    db_path = app_data_dir / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=sync_run_id,
    )

    result = runner.invoke(app, ["contacts", "list"])

    assert result.exit_code == 0
    assert "Alice Example" in result.stdout


def test_contacts_sync_command(monkeypatch: object, tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    db_path = tmp_path / "contacts.sqlite3"
    token_path = tmp_path / "token.json"

    def fake_sync_google_contacts(**_: object) -> SyncStats:
        return SyncStats(fetched_count=3, written_count=3, deactivated_count=0, sync_run_id=1)

    monkeypatch.setattr("match_my_contacts.cli.sync_google_contacts", fake_sync_google_contacts)

    result = runner.invoke(
        app,
        [
            "contacts",
            "sync",
            "--credentials",
            str(credentials_path),
            "--db-path",
            str(db_path),
            "--token-path",
            str(token_path),
        ],
    )

    assert result.exit_code == 0
    assert "3 fetched, 3 written, 0 deactivated" in result.stdout


def test_contacts_sync_google_command(monkeypatch: object, tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    db_path = tmp_path / "contacts.sqlite3"
    token_path = tmp_path / "token.json"

    def fake_sync_google_contacts(**_: object) -> SyncStats:
        return SyncStats(fetched_count=2, written_count=2, deactivated_count=1, sync_run_id=1)

    monkeypatch.setattr("match_my_contacts.cli.sync_google_contacts", fake_sync_google_contacts)

    result = runner.invoke(
        app,
        [
            "contacts",
            "sync-google",
            "--credentials",
            str(credentials_path),
            "--db-path",
            str(db_path),
            "--token-path",
            str(token_path),
        ],
    )

    assert result.exit_code == 0
    assert "2 fetched, 2 written, 1 deactivated" in result.stdout


def test_contacts_sync_uses_default_credentials_file(monkeypatch: object, tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    db_path = tmp_path / "contacts.sqlite3"
    token_path = tmp_path / "token.json"
    captured: dict[str, Path] = {}

    def fake_sync_google_contacts(**kwargs: object) -> SyncStats:
        captured["credentials_path"] = kwargs["credentials_path"]  # type: ignore[index]
        return SyncStats(fetched_count=1, written_count=1, deactivated_count=0, sync_run_id=1)

    monkeypatch.setattr("match_my_contacts.cli.sync_google_contacts", fake_sync_google_contacts)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "contacts",
            "sync",
            "--db-path",
            str(db_path),
            "--token-path",
            str(token_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["credentials_path"] == default_credentials_path()


def test_contacts_sync_uses_configured_credentials_file(monkeypatch: object, tmp_path: Path) -> None:
    from match_my_contacts.config import write_app_paths

    credentials_path = tmp_path / "shared-credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    captured: dict[str, Path] = {}

    def fake_sync_google_contacts(**kwargs: object) -> SyncStats:
        captured["credentials_path"] = kwargs["credentials_path"]  # type: ignore[index]
        return SyncStats(fetched_count=1, written_count=1, deactivated_count=0, sync_run_id=1)

    monkeypatch.setattr("match_my_contacts.cli.sync_google_contacts", fake_sync_google_contacts)
    write_app_paths(data_dir=tmp_path / "shared-data", credentials_path=credentials_path)

    result = runner.invoke(app, ["contacts", "sync"])

    assert result.exit_code == 0
    assert captured["credentials_path"] == credentials_path


def test_contacts_sync_requires_credentials_when_default_is_missing(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["contacts", "sync"])

    assert result.exit_code != 0
    assert "Google OAuth credentials file not found" in result.output


def test_contacts_list_command_reads_local_database(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[],
        sync_run_id=sync_run_id,
    )

    result = runner.invoke(app, ["contacts", "list", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "No contacts found." in result.stdout


def test_contacts_import_google_csv_command(
    tmp_path: Path,
    google_contacts_csv_path: Path,
) -> None:
    db_path = tmp_path / "contacts.sqlite3"

    result = runner.invoke(
        app,
        [
            "contacts",
            "import-google-csv",
            "--csv-path",
            str(google_contacts_csv_path),
            "--db-path",
            str(db_path),
        ],
    )

    repository = ContactsRepository(db_path)
    repository.initialize()
    contacts = repository.list_contacts()

    assert result.exit_code == 0
    assert "10 fetched, 10 written, 0 deactivated" in result.stdout
    assert len(contacts) == 10
    assert contacts[0]["source"] == "google_contacts_csv"


def test_contacts_import_google_csv_rejects_old_non_google_format(tmp_path: Path) -> None:
    csv_path = tmp_path / "legacy-contacts.csv"
    db_path = tmp_path / "contacts.sqlite3"
    csv_path.write_text(
        "\n".join(
            [
                "Name,Given Name,Family Name,E-mail 1 - Type,E-mail 1 - Value",
                "Legacy Contact,Legacy,Contact,Home,legacy@example.com",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "contacts",
            "import-google-csv",
            "--csv-path",
            str(csv_path),
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported contacts CSV" in result.stdout


def test_contacts_list_can_filter_by_source(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    google_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=google_sync_id,
    )
    csv_sync_id = repository.begin_sync_run(source="google_contacts_csv", source_account="default")
    repository.replace_contacts(
        source="google_contacts_csv",
        source_account="default",
        contacts=[
            ContactRecord(
                source="google_contacts_csv",
                source_contact_id="csv/1",
                display_name="Bob Example",
                raw_payload={"row": 1},
            )
        ],
        sync_run_id=csv_sync_id,
    )

    result = runner.invoke(
        app,
        ["contacts", "list", "--db-path", str(db_path), "--source", "google_contacts_csv"],
    )

    assert result.exit_code == 0
    assert "Bob Example" in result.stdout
    assert "Alice Example" not in result.stdout
    assert "Google Contacts CSV (default)" in result.stdout


def test_contacts_list_sources_command(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    google_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=google_sync_id,
    )
    repository.finish_sync_run(
        sync_run_id=google_sync_id,
        status="completed",
        contacts_fetched=1,
        contacts_written=1,
        contacts_deactivated=0,
    )
    csv_sync_id = repository.begin_sync_run(source="google_contacts_csv", source_account="default")
    repository.replace_contacts(
        source="google_contacts_csv",
        source_account="default",
        contacts=[
            ContactRecord(
                source="google_contacts_csv",
                source_contact_id="csv/1",
                display_name="Bob Example",
                raw_payload={"row": 1},
            )
        ],
        sync_run_id=csv_sync_id,
    )
    repository.finish_sync_run(
        sync_run_id=csv_sync_id,
        status="completed",
        contacts_fetched=1,
        contacts_written=1,
        contacts_deactivated=0,
    )

    result = runner.invoke(app, ["contacts", "list-sources", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "google_people/default: Google Contacts API [syncable_api]" in result.stdout
    assert "google_contacts_csv/default: Google Contacts CSV [snapshot_import]" in result.stdout


def test_contacts_empty_db_command_can_be_cancelled(tmp_path: Path) -> None:
    contacts_db_path = tmp_path / "contacts.sqlite3"
    results_db_path = tmp_path / "race_results.sqlite3"
    contacts_repository = ContactsRepository(contacts_db_path)
    contacts_repository.initialize()
    sync_run_id = contacts_repository.begin_sync_run(source="google_people", source_account="default")
    contacts_repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=sync_run_id,
    )

    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    dataset_id = results_repository.save_dataset(
        dataset=make_race_dataset(),
        results=make_race_results(),
    )
    result_id = results_repository.list_results(dataset_id=dataset_id, limit=1)[0]["id"]
    results_repository.set_match_review(
        dataset_id=dataset_id,
        result_id=result_id,
        status="accepted",
        contact_id=1,
        note="keep",
    )

    result = runner.invoke(
        app,
        [
            "contacts",
            "empty-db",
            "--db-path",
            str(contacts_db_path),
            "--results-db-path",
            str(results_db_path),
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "Empty DB cancelled." in result.stdout
    assert len(contacts_repository.list_contacts()) == 1
    assert len(results_repository.list_match_reviews(dataset_id=dataset_id)) == 1


def test_contacts_empty_db_command_clears_contacts_and_reviews(tmp_path: Path) -> None:
    contacts_db_path = tmp_path / "contacts.sqlite3"
    results_db_path = tmp_path / "race_results.sqlite3"
    contacts_repository = ContactsRepository(contacts_db_path)
    contacts_repository.initialize()
    sync_run_id = contacts_repository.begin_sync_run(source="google_people", source_account="default")
    contacts_repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=sync_run_id,
    )
    contact_id = int(contacts_repository.list_contacts()[0]["id"])
    contacts_repository.add_alias(contact_id=contact_id, alias_text="Alice Ex")

    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    dataset_id = results_repository.save_dataset(
        dataset=make_race_dataset(),
        results=make_race_results(),
    )
    result_id = results_repository.list_results(dataset_id=dataset_id, limit=1)[0]["id"]
    results_repository.set_match_review(
        dataset_id=dataset_id,
        result_id=result_id,
        status="accepted",
        contact_id=contact_id,
        note="wipe",
    )

    result = runner.invoke(
        app,
        [
            "contacts",
            "empty-db",
            "--db-path",
            str(contacts_db_path),
            "--results-db-path",
            str(results_db_path),
            "--yes",
        ],
    )

    contacts_repository = ContactsRepository(contacts_db_path)
    contacts_repository.initialize()
    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()

    assert result.exit_code == 0
    assert "Empty DB completed: 1 contacts, 0 methods, 1 aliases, 1 sync runs, 1 matching reviews deleted." in result.stdout
    assert contacts_repository.list_contacts(include_inactive=True) == []
    assert results_repository.list_match_reviews(dataset_id=dataset_id) == []

    next_sync_id = contacts_repository.begin_sync_run(source="google_people", source_account="default")
    contacts_repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/2",
                display_name="Bob Example",
                raw_payload={"resourceName": "people/2"},
            )
        ],
        sync_run_id=next_sync_id,
    )
    assert int(contacts_repository.list_contacts()[0]["id"]) == 1


def test_contacts_vacuum_db_command(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=sync_run_id,
    )

    result = runner.invoke(
        app,
        [
            "contacts",
            "vacuum-db",
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "VACUUM completed:" in result.stdout
    assert "bytes reclaimed" in result.stdout


def test_race_results_fetch_acn_command(monkeypatch: object, tmp_path: Path) -> None:
    db_path = tmp_path / "race_results.sqlite3"
    raw_dir = tmp_path / "raw"

    def fake_fetch_acn_results(**_: object) -> RaceFetchStats:
        return RaceFetchStats(dataset_id=7, results_count=42)

    monkeypatch.setattr("match_my_contacts.cli.fetch_acn_results", fake_fetch_acn_results)

    result = runner.invoke(
        app,
        [
            "race-results",
            "fetch-acn",
            "--url",
            "https://www.acn-timing.com/?lng=FR#/events/1/ctx/demo/generic/abc/home/LIVE1",
            "--db-path",
            str(db_path),
            "--raw-dir",
            str(raw_dir),
        ],
    )

    assert result.exit_code == 0
    assert "dataset 7" in result.stdout


def test_race_results_list_datasets_command(tmp_path: Path) -> None:
    db_path = tmp_path / "race_results.sqlite3"
    repository = RaceResultsRepository(db_path)
    repository.initialize()

    result = runner.invoke(app, ["race-results", "list-datasets", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "No race datasets found." in result.stdout


def test_matching_run_command(monkeypatch: object) -> None:
    def fake_match_dataset(**_: object) -> MatchReport:
        return MatchReport(
            dataset={"event_title": "Demo Race", "event_date": "12/04/2026", "event_location": "Liege"},
            accepted_matches=[
                MatchResult(
                    status="accepted",
                    match_method="exact",
                    score=100.0,
                    matched_alias="Jean Dupont",
                    confidence_gap=100.0,
                    result_id=1,
                    dataset_id=7,
                    athlete_name="Jean Dupont",
                    position_text="1.",
                    bib="101",
                    finish_time="0:40:00",
                    team="Club A",
                    category="SEH",
                    contact_id=1,
                    contact_name="Jean Dupont",
                )
            ],
            ambiguous_matches=[],
            unmatched_count=10,
            contacts_count=20,
            results_count=11,
        )

    monkeypatch.setattr("match_my_contacts.cli.match_dataset", fake_match_dataset)

    result = runner.invoke(app, ["matching", "run", "--dataset-id", "7"])

    assert result.exit_code == 0
    assert "1 accepted matches" in result.stdout
    assert "Jean Dupont" in result.stdout


def test_contacts_add_alias_command(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=sync_run_id,
    )

    contact_id = repository.list_contacts()[0]["id"]
    result = runner.invoke(
        app,
        [
            "contacts",
            "add-alias",
            "--contact-id",
            str(contact_id),
            "--alias",
            "Alice Ex",
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Added alias" in result.stdout
    assert repository.get_contact(contact_id=contact_id)["aliases"] == ["Alice Ex"]


def test_race_results_add_alias_command(tmp_path: Path) -> None:
    db_path = tmp_path / "race_results.sqlite3"
    repository = RaceResultsRepository(db_path)
    repository.initialize()
    dataset_id = repository.save_dataset(
        dataset=make_race_dataset(),
        results=[],
    )

    result = runner.invoke(
        app,
        [
            "race-results",
            "add-alias",
            "--dataset-id",
            str(dataset_id),
            "--alias",
            "demo-race",
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert repository.resolve_dataset_selector("demo-race") == dataset_id


def make_race_dataset():
    from match_my_contacts.race_results.models import RaceDataset

    return RaceDataset(
        provider="acn_timing",
        source_url="https://example.test",
        external_event_id="1",
        context_db="demo",
        report_key="LIVE1",
        report_path="path",
        event_title="Demo Race",
        event_date="12/04/2026",
        event_location="Liege",
        event_country="BEL",
        total_results=0,
        metadata={},
    )


def make_race_results():
    from match_my_contacts.race_results.models import RaceResultRow

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
        )
    ]
