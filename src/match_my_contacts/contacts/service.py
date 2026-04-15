from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from match_my_contacts.config import AppPaths, default_credentials_path

from .models import ContactMethod, ContactRecord
from .normalization import normalize_email, normalize_phone
from .google_people import fetch_google_contacts
from .models import SyncStats
from .sources import GOOGLE_CONTACTS_CSV_SOURCE, GOOGLE_PEOPLE_SOURCE
from .storage import ContactsRepository

GOOGLE_CSV_SOURCE = GOOGLE_CONTACTS_CSV_SOURCE
_GOOGLE_MULTI_VALUE_RE = re.compile(r"^(E-mail|Phone) (\d+) - (Type|Value)$")
_GOOGLE_ORGANIZATION_NAME_RE = re.compile(r"^Organization (\d+) - Name$")


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


def load_google_contacts_csv(
    *,
    csv_path: Path,
    source_account: str = "default",
) -> list[ContactRecord]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV file is empty: {csv_path}")
        if "Name" not in reader.fieldnames:
            raise ValueError(
                "Unsupported contacts CSV. Expected a Google Contacts export with a 'Name' column."
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
    display_name = (
        row.get("Name")
        or " ".join(part for part in [row.get("Given Name"), row.get("Family Name")] if part).strip()
        or f"csv-contact-{row_number}"
    )
    organization = _extract_google_csv_organization(row)
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
        given_name=row.get("Given Name") or None,
        family_name=row.get("Family Name") or None,
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
    for kind, _ in sorted(grouped_entries):
        entry = grouped_entries[(kind, _)]
        raw_value = entry.get("value", "").strip()
        if not raw_value:
            continue
        normalized_value = normalize_email(raw_value) if kind == "email" else normalize_phone(raw_value)
        methods.append(
            ContactMethod(
                kind=kind,
                value=raw_value,
                label=entry.get("type") or None,
                normalized_value=normalized_value,
                is_primary=not any(existing.kind == kind for existing in methods),
            )
        )
    return methods


def _extract_google_csv_organization(row: dict[str, str]) -> str | None:
    organizations: list[tuple[int, str]] = []
    for key, value in row.items():
        match = _GOOGLE_ORGANIZATION_NAME_RE.match(key)
        if match is None or not value:
            continue
        organizations.append((int(match.group(1)), value))
    if organizations:
        return sorted(organizations)[0][1]
    return None


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
        "given_name": row.get("Given Name", ""),
        "family_name": row.get("Family Name", ""),
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
