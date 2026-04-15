from __future__ import annotations

import json
from pathlib import Path

from match_my_contacts.contacts.models import ContactMethod, ContactRecord
from match_my_contacts.contacts.sources import SOURCE_BEHAVIOR_SYNCABLE_API
from match_my_contacts.contacts.service import vacuum_contacts_database
from match_my_contacts.contacts.storage import ContactsRepository


def make_contact(
    source_contact_id: str,
    display_name: str,
    *,
    email: str | None = None,
) -> ContactRecord:
    methods = []
    if email:
        methods.append(
            ContactMethod(
                kind="email",
                value=email,
                normalized_value=email.lower(),
                is_primary=True,
            )
        )
    return ContactRecord(
        source_contact_id=source_contact_id,
        display_name=display_name,
        methods=methods,
        raw_payload={"resourceName": source_contact_id, "displayName": display_name},
    )


def test_replace_contacts_is_idempotent_and_deactivates_missing(tmp_path: Path) -> None:
    repository = ContactsRepository(tmp_path / "contacts.sqlite3")
    repository.initialize()

    first_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    first_stats = repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            make_contact("people/1", "Alice Example", email="alice@example.com"),
            make_contact("people/2", "Bob Example"),
        ],
        sync_run_id=first_sync_id,
    )
    repository.finish_sync_run(
        sync_run_id=first_sync_id,
        status="completed",
        contacts_fetched=first_stats.fetched_count,
        contacts_written=first_stats.written_count,
        contacts_deactivated=first_stats.deactivated_count,
    )

    second_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    second_stats = repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            make_contact("people/1", "Alice Example", email="alice@example.com"),
        ],
        sync_run_id=second_sync_id,
    )

    contacts = repository.list_contacts(include_inactive=True)

    assert first_stats.fetched_count == 2
    assert first_stats.deactivated_count == 0
    assert second_stats.fetched_count == 1
    assert second_stats.deactivated_count == 1
    assert [contact["display_name"] for contact in contacts] == ["Alice Example", "Bob Example"]
    assert contacts[0]["active"] is True
    assert contacts[1]["active"] is False


def test_write_export_json_includes_methods(tmp_path: Path) -> None:
    repository = ContactsRepository(tmp_path / "contacts.sqlite3")
    repository.initialize()

    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/1", "Alice Example", email="alice@example.com")],
        sync_run_id=sync_run_id,
    )

    output_path = repository.write_export_json(output_path=tmp_path / "contacts.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload[0]["display_name"] == "Alice Example"
    assert payload[0]["methods"][0]["value"] == "alice@example.com"


def test_aliases_can_be_added_listed_and_removed(tmp_path: Path) -> None:
    repository = ContactsRepository(tmp_path / "contacts.sqlite3")
    repository.initialize()

    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/1", "Alice Example", email="alice@example.com")],
        sync_run_id=sync_run_id,
    )

    contact = repository.list_contacts()[0]
    repository.add_alias(contact_id=contact["id"], alias_text="Alice Ex")
    aliases = repository.list_aliases(contact_id=contact["id"])

    assert aliases[0]["alias_text"] == "Alice Ex"
    assert repository.get_contact(contact_id=contact["id"])["aliases"] == ["Alice Ex"]
    assert repository.remove_alias(contact_id=contact["id"], alias_text="Alice Ex") is True


def test_get_contact_details_returns_enriched_fields(tmp_path: Path) -> None:
    repository = ContactsRepository(tmp_path / "contacts.sqlite3")
    repository.initialize()

    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/1", "Alice Example", email="alice@example.com")],
        sync_run_id=sync_run_id,
    )

    contact = repository.list_contacts()[0]
    repository.add_alias(contact_id=contact["id"], alias_text="Alice Ex")

    details = repository.get_contact_details(contact_id=contact["id"])

    assert details["source"] == "google_people"
    assert details["source_label"] == "Google Contacts API"
    assert details["source_behavior"] == SOURCE_BEHAVIOR_SYNCABLE_API
    assert details["source_syncable"] is True
    assert details["source_display"] == "Google Contacts API (default)"
    assert details["source_contact_id"] == "people/1"
    assert details["created_at"]
    assert details["updated_at"]
    assert details["raw_json"]["resourceName"] == "people/1"
    assert details["raw_json_text"]
    assert details["methods"][0]["created_at"]
    assert details["methods"][0]["is_primary"] is True
    assert details["alias_records"][0]["alias_text"] == "Alice Ex"
    assert details["aliases"] == ["Alice Ex"]


def test_list_source_summaries_returns_counts_and_last_run(tmp_path: Path) -> None:
    repository = ContactsRepository(tmp_path / "contacts.sqlite3")
    repository.initialize()

    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/1", "Alice Example", email="alice@example.com")],
        sync_run_id=sync_run_id,
    )
    repository.finish_sync_run(
        sync_run_id=sync_run_id,
        status="completed",
        contacts_fetched=1,
        contacts_written=1,
        contacts_deactivated=0,
    )

    summaries = repository.list_source_summaries()

    assert len(summaries) == 1
    assert summaries[0]["source"] == "google_people"
    assert summaries[0]["source_label"] == "Google Contacts API"
    assert summaries[0]["source_behavior"] == SOURCE_BEHAVIOR_SYNCABLE_API
    assert summaries[0]["active_contacts"] == 1
    assert summaries[0]["inactive_contacts"] == 0
    assert summaries[0]["last_run_status"] == "completed"


def test_empty_database_removes_contacts_aliases_methods_and_sync_runs(tmp_path: Path) -> None:
    repository = ContactsRepository(tmp_path / "contacts.sqlite3")
    repository.initialize()

    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/1", "Alice Example", email="alice@example.com")],
        sync_run_id=sync_run_id,
    )
    contact = repository.list_contacts()[0]
    repository.add_alias(contact_id=contact["id"], alias_text="Alice Ex")

    stats = repository.empty_database()

    assert stats["contacts_deleted"] == 1
    assert stats["methods_deleted"] == 1
    assert stats["aliases_deleted"] == 1
    assert stats["sync_runs_deleted"] == 1
    assert stats["ids_reset"] is True
    assert repository.list_contacts(include_inactive=True) == []

    next_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/2", "Bob Example", email="bob@example.com")],
        sync_run_id=next_sync_id,
    )
    assert int(repository.list_contacts()[0]["id"]) == 1


def test_vacuum_contacts_database_returns_size_stats(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[make_contact("people/1", "Alice Example", email="alice@example.com")],
        sync_run_id=sync_run_id,
    )

    stats = vacuum_contacts_database(db_path=db_path)

    assert stats.before_size_bytes >= 0
    assert stats.after_size_bytes >= 0
    assert stats.reclaimed_bytes >= 0
    assert db_path.exists() is True
