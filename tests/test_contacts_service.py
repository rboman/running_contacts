from __future__ import annotations

from pathlib import Path

from match_my_contacts.contacts.service import GOOGLE_CSV_SOURCE, import_google_contacts_csv
from match_my_contacts.contacts.sources import SOURCE_BEHAVIOR_SNAPSHOT_IMPORT
from match_my_contacts.contacts.storage import ContactsRepository


def test_import_google_contacts_csv_maps_supported_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "google-contacts.csv"
    db_path = tmp_path / "contacts.sqlite3"
    csv_path.write_text(
        "\n".join(
            [
                "Name,Given Name,Family Name,Nickname,Notes,Organization 1 - Name,E-mail 1 - Type,E-mail 1 - Value,Phone 1 - Type,Phone 1 - Value",
                "Alice Example,Alice,Example,Ali,Fast runner,Acme Running,Home,alice@example.com,Mobile,+32 470 12 34 56",
                "Bob Example,Bob,Example,,Prefers email,Beta Club,Work,bob@example.com,Mobile,+32 470 99 98 88",
            ]
        ),
        encoding="utf-8",
    )

    first_stats = import_google_contacts_csv(csv_path=csv_path, db_path=db_path)
    second_stats = import_google_contacts_csv(csv_path=csv_path, db_path=db_path)

    repository = ContactsRepository(db_path)
    repository.initialize()
    contacts = repository.list_contacts()
    alice = repository.list_contacts(query="Alice")[0]
    alice_details = repository.get_contact_details(contact_id=alice["id"])

    assert first_stats.written_count == 2
    assert second_stats.written_count == 2
    assert len(contacts) == 2
    assert alice_details["source"] == GOOGLE_CSV_SOURCE
    assert alice_details["source_behavior"] == SOURCE_BEHAVIOR_SNAPSHOT_IMPORT
    assert alice_details["source_syncable"] is False
    assert alice_details["display_name"] == "Alice Example"
    assert alice_details["organization"] == "Acme Running"
    assert alice_details["notes"] == "Fast runner"
    assert [(method["kind"], method["normalized_value"]) for method in alice_details["methods"]] == [
        ("email", "alice@example.com"),
        ("phone", "+32470123456"),
    ]


def test_google_csv_import_coexists_with_google_people_contacts(tmp_path: Path) -> None:
    csv_path = tmp_path / "google-contacts.csv"
    db_path = tmp_path / "contacts.sqlite3"
    csv_path.write_text(
        "\n".join(
            [
                "Name,Given Name,Family Name,E-mail 1 - Type,E-mail 1 - Value",
                "Alice Example,Alice,Example,Home,alice@example.com",
            ]
        ),
        encoding="utf-8",
    )

    repository = ContactsRepository(db_path)
    repository.initialize()
    first_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            repository_contact("people/1", "Alice Example", "alice@example.com"),
        ],
        sync_run_id=first_sync_id,
    )
    repository.finish_sync_run(
        sync_run_id=first_sync_id,
        status="completed",
        contacts_fetched=1,
        contacts_written=1,
        contacts_deactivated=0,
    )

    import_google_contacts_csv(csv_path=csv_path, db_path=db_path)
    second_sync_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            repository_contact("people/1", "Alice Example", "alice@example.com"),
        ],
        sync_run_id=second_sync_id,
    )
    repository.finish_sync_run(
        sync_run_id=second_sync_id,
        status="completed",
        contacts_fetched=1,
        contacts_written=1,
        contacts_deactivated=0,
    )

    contacts = repository.list_contacts(include_inactive=True)

    assert len(contacts) == 2
    assert {contact["source"] for contact in contacts} == {"google_people", "google_contacts_csv"}
    assert all(contact["active"] is True for contact in contacts)


def repository_contact(source_contact_id: str, display_name: str, email: str):
    from match_my_contacts.contacts.models import ContactMethod, ContactRecord

    return ContactRecord(
        source_contact_id=source_contact_id,
        display_name=display_name,
        methods=[
            ContactMethod(
                kind="email",
                value=email,
                normalized_value=email.lower(),
                is_primary=True,
            )
        ],
        raw_payload={"resourceName": source_contact_id},
    )
