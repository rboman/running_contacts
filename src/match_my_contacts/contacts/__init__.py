"""Contacts synchronization and local storage."""

from .models import ContactMethod, ContactRecord, SyncStats
from .service import (
    GoogleSyncPaths,
    ensure_google_credentials_file,
    import_google_contacts_csv,
    load_google_contacts_csv,
    resolve_google_sync_paths,
    sync_google_contacts,
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
    "GOOGLE_CONTACTS_CSV_SOURCE",
    "GOOGLE_PEOPLE_SOURCE",
    "GoogleSyncPaths",
    "SyncStats",
    "build_source_display",
    "ensure_google_credentials_file",
    "get_contact_source_definition",
    "import_google_contacts_csv",
    "list_contact_source_definitions",
    "load_google_contacts_csv",
    "resolve_google_sync_paths",
    "sync_google_contacts",
]
