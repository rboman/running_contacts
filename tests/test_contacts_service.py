from __future__ import annotations

from pathlib import Path

from match_my_contacts.contacts.service import GOOGLE_CSV_SOURCE, import_google_contacts_csv
from match_my_contacts.contacts.sources import SOURCE_BEHAVIOR_SNAPSHOT_IMPORT
from match_my_contacts.contacts.storage import ContactsRepository


def test_import_google_contacts_csv_maps_supported_fields(
    tmp_path: Path,
    google_contacts_csv_path: Path,
) -> None:
    db_path = tmp_path / "contacts.sqlite3"

    first_stats = import_google_contacts_csv(csv_path=google_contacts_csv_path, db_path=db_path)
    second_stats = import_google_contacts_csv(csv_path=google_contacts_csv_path, db_path=db_path)

    repository = ContactsRepository(db_path)
    repository.initialize()
    contacts = repository.list_contacts()
    actarus = repository.list_contacts(query="Actarus")[0]
    actarus_details = repository.get_contact_details(contact_id=actarus["id"])
    captain_flam = repository.list_contacts(query="Capitaine")[0]
    captain_flam_details = repository.get_contact_details(contact_id=captain_flam["id"])
    fallback_email = repository.list_contacts(query="hangar18@retro.test")[0]
    fallback_email_details = repository.get_contact_details(contact_id=fallback_email["id"])

    assert first_stats.written_count == 10
    assert second_stats.written_count == 10
    assert len(contacts) == 10
    assert actarus_details["source"] == GOOGLE_CSV_SOURCE
    assert actarus_details["source_behavior"] == SOURCE_BEHAVIOR_SNAPSHOT_IMPORT
    assert actarus_details["source_syncable"] is False
    assert actarus_details["display_name"] == "Actarus Vega"
    assert actarus_details["organization"] == "Institut Vega"
    assert actarus_details["notes"] == "Pilote de test\nAime les étoiles."
    assert [(method["kind"], method["normalized_value"]) for method in actarus_details["methods"]] == [
        ("email", "actarus.vega@vega.test"),
        ("phone", "+32470000001"),
    ]
    assert captain_flam_details["display_name"] == "Capitaine Flam"
    assert [method["value"] for method in captain_flam_details["methods"]] == [
        "cap.flam@comet.test",
        "flam@starfleet.test",
        "+33 6 10 20 30 40",
    ]
    assert fallback_email_details["display_name"] == "hangar18@retro.test"
    assert fallback_email_details["organization"] is None


def test_google_csv_import_coexists_with_google_people_contacts(
    tmp_path: Path,
    google_contacts_csv_path: Path,
) -> None:
    db_path = tmp_path / "contacts.sqlite3"

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

    import_google_contacts_csv(csv_path=google_contacts_csv_path, db_path=db_path)
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

    assert len(contacts) == 11
    assert {contact["source"] for contact in contacts} == {"google_people", "google_contacts_csv"}
    assert all(contact["active"] is True for contact in contacts)


def test_import_google_contacts_csv_rejects_legacy_schema(tmp_path: Path) -> None:
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

    try:
        import_google_contacts_csv(csv_path=csv_path, db_path=db_path)
    except ValueError as exc:
        assert "Unsupported contacts CSV" in str(exc)
    else:
        raise AssertionError("Expected legacy CSV schema to be rejected")


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
