"""Contacts synchronization and local storage."""

from .models import ContactMethod, ContactRecord, EmptyContactsDbStats, SyncStats, VacuumDbStats
from .service import (
    GoogleSyncPaths,
    empty_contacts_database,
    ensure_google_credentials_file,
    import_google_contacts_csv,
    load_google_contacts_csv,
    resolve_google_sync_paths,
    sync_google_contacts,
    vacuum_contacts_database,
)
from .sources import (
    GOOGLE_CONTACTS_CSV_SOURCE,
    GOOGLE_PEOPLE_SOURCE,
    ContactSourceDefinition,
    build_source_display,
    get_contact_source_definition,
    list_contact_source_definitions,
)
from .storage import ContactsRepository

__all__ = [
    "ContactMethod",
    "ContactRecord",
    "ContactSourceDefinition",
    "ContactsRepository",
    "EmptyContactsDbStats",
    "GOOGLE_CONTACTS_CSV_SOURCE",
    "GOOGLE_PEOPLE_SOURCE",
    "GoogleSyncPaths",
    "SyncStats",
    "VacuumDbStats",
    "build_source_display",
    "empty_contacts_database",
    "ensure_google_credentials_file",
    "get_contact_source_definition",
    "import_google_contacts_csv",
    "list_contact_source_definitions",
    "load_google_contacts_csv",
    "resolve_google_sync_paths",
    "sync_google_contacts",
    "vacuum_contacts_database",
]
