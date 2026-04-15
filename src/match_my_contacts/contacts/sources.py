from __future__ import annotations

from dataclasses import dataclass


GOOGLE_PEOPLE_SOURCE = "google_people"
GOOGLE_CONTACTS_CSV_SOURCE = "google_contacts_csv"

SOURCE_BEHAVIOR_SYNCABLE_API = "syncable_api"
SOURCE_BEHAVIOR_SNAPSHOT_IMPORT = "snapshot_import"
SOURCE_BEHAVIOR_MANUAL_ENTRY = "manual_entry"
SOURCE_BEHAVIOR_UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class ContactSourceDefinition:
    key: str
    label: str
    family: str
    behavior: str
    syncable: bool


_SOURCE_REGISTRY: dict[str, ContactSourceDefinition] = {
    GOOGLE_PEOPLE_SOURCE: ContactSourceDefinition(
        key=GOOGLE_PEOPLE_SOURCE,
        label="Google Contacts API",
        family="google",
        behavior=SOURCE_BEHAVIOR_SYNCABLE_API,
        syncable=True,
    ),
    GOOGLE_CONTACTS_CSV_SOURCE: ContactSourceDefinition(
        key=GOOGLE_CONTACTS_CSV_SOURCE,
        label="Google Contacts CSV",
        family="google",
        behavior=SOURCE_BEHAVIOR_SNAPSHOT_IMPORT,
        syncable=False,
    ),
}


def get_contact_source_definition(source: str) -> ContactSourceDefinition:
    if source in _SOURCE_REGISTRY:
        return _SOURCE_REGISTRY[source]
    normalized = source.replace("_", " ").strip() or "unknown source"
    label = normalized[:1].upper() + normalized[1:]
    return ContactSourceDefinition(
        key=source,
        label=label,
        family=source or "unknown",
        behavior=SOURCE_BEHAVIOR_UNKNOWN,
        syncable=False,
    )


def list_contact_source_definitions() -> list[ContactSourceDefinition]:
    return list(_SOURCE_REGISTRY.values())


def build_source_display(*, source: str, source_account: str | None) -> str:
    definition = get_contact_source_definition(source)
    if source_account:
        return f"{definition.label} ({source_account})"
    return definition.label
