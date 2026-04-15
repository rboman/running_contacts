from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from match_my_contacts.config import AppPaths, default_credentials_path

from .models import ContactMethod, ContactRecord, EmptyContactsDbStats, VacuumDbStats
from .normalization import normalize_email, normalize_phone
from .google_people import fetch_google_contacts
from .models import SyncStats
from .sources import GOOGLE_CONTACTS_CSV_SOURCE, GOOGLE_PEOPLE_SOURCE
from .storage import ContactsRepository
from match_my_contacts.race_results.storage import RaceResultsRepository

GOOGLE_CSV_SOURCE = GOOGLE_CONTACTS_CSV_SOURCE
_GOOGLE_MULTI_VALUE_RE = re.compile(r"^(E-mail|Phone) (\d+) - (Label|Value)$")
_GOOGLE_REQUIRED_HEADERS = (
    "First Name",
    "Middle Name",
    "Last Name",
    "Nickname",
    "Organization Name",
    "Notes",
    "E-mail 1 - Label",
    "E-mail 1 - Value",
    "Phone 1 - Label",
    "Phone 1 - Value",
)


@dataclass(slots=True, frozen=True)
class GoogleSyncPaths:
    db_path: Path
    token_path: Path
    credentials_path: Path


def resolve_google_sync_paths(
    *,
    app_paths: AppPaths,
    db_path: Path | None = None,
    token_path: Path | None = None,
    credentials_path: Path | None = None,
) -> GoogleSyncPaths:
    return GoogleSyncPaths(
        db_path=db_path or app_paths.contacts_db,
        token_path=token_path or app_paths.google_token,
        credentials_path=credentials_path or app_paths.credentials_path or default_credentials_path(),
    )


def ensure_google_credentials_file(credentials_path: Path) -> Path:
    if not credentials_path.exists() or not credentials_path.is_file():
        raise ValueError(
            "Google OAuth credentials file not found. "
            "Pass --credentials /path/to/credentials.json or place credentials.json at the repository root."
        )
    return credentials_path


def sync_google_contacts(
    *,
    credentials_path: Path,
    token_path: Path,
    db_path: Path,
    source_account: str = "default",
) -> SyncStats:
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source=GOOGLE_PEOPLE_SOURCE, source_account=source_account)

    try:
        contacts = fetch_google_contacts(
            credentials_path=credentials_path,
            token_path=token_path,
            source_account=source_account,
        )
        stats = repository.replace_contacts(
            source=GOOGLE_PEOPLE_SOURCE,
            source_account=source_account,
            contacts=contacts,
            sync_run_id=sync_run_id,
        )
    except Exception as exc:
        repository.finish_sync_run(
            sync_run_id=sync_run_id,
            status="failed",
            contacts_fetched=0,
            contacts_written=0,
            contacts_deactivated=0,
            error_message=str(exc),
        )
        raise

    repository.finish_sync_run(
        sync_run_id=sync_run_id,
        status="completed",
        contacts_fetched=stats.fetched_count,
        contacts_written=stats.written_count,
        contacts_deactivated=stats.deactivated_count,
    )
    return stats


def import_google_contacts_csv(
    *,
    csv_path: Path,
    db_path: Path,
    source_account: str = "default",
) -> SyncStats:
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source=GOOGLE_CSV_SOURCE, source_account=source_account)

    try:
        contacts = load_google_contacts_csv(csv_path=csv_path, source_account=source_account)
        stats = repository.replace_contacts(
            source=GOOGLE_CSV_SOURCE,
            source_account=source_account,
            contacts=contacts,
            sync_run_id=sync_run_id,
        )
    except Exception as exc:
        repository.finish_sync_run(
            sync_run_id=sync_run_id,
            status="failed",
            contacts_fetched=0,
            contacts_written=0,
            contacts_deactivated=0,
            error_message=str(exc),
        )
        raise

    repository.finish_sync_run(
        sync_run_id=sync_run_id,
        status="completed",
        contacts_fetched=stats.fetched_count,
        contacts_written=stats.written_count,
        contacts_deactivated=stats.deactivated_count,
    )
    return stats


def empty_contacts_database(
    *,
    db_path: Path,
    results_db_path: Path,
) -> EmptyContactsDbStats:
    repository = ContactsRepository(db_path)
    repository.initialize()
    counts = repository.empty_database()

    match_reviews_deleted = 0
    if results_db_path.exists():
        results_repository = RaceResultsRepository(results_db_path)
        results_repository.initialize()
        match_reviews_deleted = results_repository.clear_all_match_reviews()

    return EmptyContactsDbStats(
        contacts_deleted=int(counts["contacts_deleted"]),
        methods_deleted=int(counts["methods_deleted"]),
        aliases_deleted=int(counts["aliases_deleted"]),
        sync_runs_deleted=int(counts["sync_runs_deleted"]),
        match_reviews_deleted=match_reviews_deleted,
        ids_reset=bool(counts["ids_reset"]),
    )


def vacuum_contacts_database(*, db_path: Path) -> VacuumDbStats:
    repository = ContactsRepository(db_path)
    repository.initialize()
    before_size_bytes = db_path.stat().st_size if db_path.exists() else 0
    repository.vacuum()
    after_size_bytes = db_path.stat().st_size if db_path.exists() else 0
    return VacuumDbStats(
        before_size_bytes=before_size_bytes,
        after_size_bytes=after_size_bytes,
    )


def load_google_contacts_csv(
    *,
    csv_path: Path,
    source_account: str = "default",
) -> list[ContactRecord]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV file is empty: {csv_path}")
        fieldnames = [str(fieldname).strip() for fieldname in reader.fieldnames]
        missing_headers = [header for header in _GOOGLE_REQUIRED_HEADERS if header not in fieldnames]
        if missing_headers:
            raise ValueError(
                "Unsupported contacts CSV. Expected the real Google Contacts export format with "
                f"headers including: {', '.join(_GOOGLE_REQUIRED_HEADERS)}. "
                f"Missing: {', '.join(missing_headers)}."
            )

        contacts: list[ContactRecord] = []
        for row_number, row in enumerate(reader, start=1):
            cleaned_row = _clean_csv_row(row)
            if not any(cleaned_row.values()):
                continue
            contacts.append(
                _google_csv_row_to_contact_record(
                    cleaned_row,
                    source_account=source_account,
                    row_number=row_number,
                )
            )
        return contacts


def _google_csv_row_to_contact_record(
    row: dict[str, str],
    *,
    source_account: str,
    row_number: int,
) -> ContactRecord:
    methods = _extract_google_csv_methods(row)
    display_name = _build_google_csv_display_name(
        row=row,
        methods=methods,
        row_number=row_number,
    )
    organization = _extract_google_csv_organization(row)
    given_name = " ".join(
        part for part in [row.get("First Name"), row.get("Middle Name")] if part
    ).strip() or None
    raw_payload = {
        "format": "google_contacts_csv",
        "row_number": row_number,
        "fields": row,
    }
    return ContactRecord(
        source=GOOGLE_CSV_SOURCE,
        source_account=source_account,
        source_contact_id=_build_google_csv_source_contact_id(
            row=row,
            display_name=display_name,
            organization=organization,
            methods=methods,
            row_number=row_number,
        ),
        display_name=display_name,
        given_name=given_name,
        family_name=row.get("Last Name") or None,
        nickname=row.get("Nickname") or None,
        organization=organization,
        notes=row.get("Notes") or None,
        methods=methods,
        raw_payload=raw_payload,
    )


def _extract_google_csv_methods(row: dict[str, str]) -> list[ContactMethod]:
    grouped_entries: dict[tuple[str, int], dict[str, str]] = {}
    for key, value in row.items():
        match = _GOOGLE_MULTI_VALUE_RE.match(key)
        if match is None or not value:
            continue
        kind_label, index_text, field_name = match.groups()
        kind = "email" if kind_label == "E-mail" else "phone"
        grouped_entries.setdefault((kind, int(index_text)), {})[field_name.lower()] = value

    methods: list[ContactMethod] = []
    seen_values: set[tuple[str, str]] = set()
    for group_key in sorted(grouped_entries):
        kind, _ = group_key
        entry = grouped_entries[group_key]
        label = (entry.get("label") or "").strip() or None
        for raw_value in _split_google_csv_multi_value(entry.get("value", "")):
            normalized_value = (
                normalize_email(raw_value) if kind == "email" else normalize_phone(raw_value)
            )
            dedupe_key = (kind, normalized_value or raw_value)
            if dedupe_key in seen_values:
                continue
            seen_values.add(dedupe_key)
            methods.append(
                ContactMethod(
                    kind=kind,
                    value=raw_value,
                    label=label,
                    normalized_value=normalized_value,
                )
            )
    primary_by_kind: set[str] = set()
    for method in methods:
        if method.kind in primary_by_kind:
            continue
        method.is_primary = True
        primary_by_kind.add(method.kind)
    return methods


def _extract_google_csv_organization(row: dict[str, str]) -> str | None:
    return row.get("Organization Name") or None


def _build_google_csv_display_name(
    *,
    row: dict[str, str],
    methods: list[ContactMethod],
    row_number: int,
) -> str:
    name = " ".join(
        part for part in [row.get("First Name"), row.get("Middle Name"), row.get("Last Name")] if part
    ).strip()
    if name:
        return name
    organization = row.get("Organization Name")
    if organization:
        return organization
    for method in methods:
        if method.kind == "email":
            return method.value
    for method in methods:
        if method.kind == "phone":
            return method.value
    return f"csv-contact-{row_number}"


def _split_google_csv_multi_value(value: str) -> list[str]:
    return [part.strip() for part in value.split(":::") if part.strip()]


def _build_google_csv_source_contact_id(
    *,
    row: dict[str, str],
    display_name: str,
    organization: str | None,
    methods: list[ContactMethod],
    row_number: int,
) -> str:
    primary_key = {
        "display_name": display_name,
        "first_name": row.get("First Name", ""),
        "middle_name": row.get("Middle Name", ""),
        "last_name": row.get("Last Name", ""),
        "nickname": row.get("Nickname", ""),
        "organization": organization or "",
        "emails": sorted(
            method.normalized_value or method.value
            for method in methods
            if method.kind == "email"
        ),
        "phones": sorted(
            method.normalized_value or method.value
            for method in methods
            if method.kind == "phone"
        ),
    }
    if not any(primary_key.values()):
        primary_key["row_number"] = row_number
        primary_key["raw_row"] = row
    digest = hashlib.sha1(
        json.dumps(primary_key, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"google-csv:{digest}"


def _clean_csv_row(row: dict[str, str | None]) -> dict[str, str]:
    return {
        str(key).strip(): (value or "").strip()
        for key, value in row.items()
        if key is not None
    }
