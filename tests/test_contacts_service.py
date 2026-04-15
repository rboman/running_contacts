from __future__ import annotations

from pathlib import Path

from match_my_contacts.contacts.service import GOOGLE_CSV_SOURCE, import_google_contacts_csv
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
    assert alice_details["display_name"] == "Alice Example"
    assert alice_details["organization"] == "Acme Running"
    assert alice_details["notes"] == "Fast runner"
    assert [(method["kind"], method["normalized_value"]) for method in alice_details["methods"]] == [
        ("email", "alice@example.com"),
        ("phone", "+32470123456"),
    ]
