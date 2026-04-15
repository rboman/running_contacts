from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from match_my_contacts.matching.normalization import normalize_person_name

from .models import ContactRecord, SyncStats
from .sources import build_source_display, get_contact_source_definition


class ContactsRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_account TEXT NOT NULL,
                    source_contact_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    given_name TEXT,
                    family_name TEXT,
                    nickname TEXT,
                    organization TEXT,
                    notes TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    last_seen_sync_id INTEGER,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source, source_account, source_contact_id)
                );

                CREATE TABLE IF NOT EXISTS contact_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    label TEXT,
                    value TEXT NOT NULL,
                    normalized_value TEXT,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_account TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    contacts_fetched INTEGER NOT NULL DEFAULT 0,
                    contacts_written INTEGER NOT NULL DEFAULT 0,
                    contacts_deactivated INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS contact_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    alias_text TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(contact_id, normalized_alias),
                    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );
                """
            )

    def begin_sync_run(self, *, source: str, source_account: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (source, source_account, status)
                VALUES (?, ?, ?)
                """,
                (source, source_account, "running"),
            )
            return int(cursor.lastrowid)

    def finish_sync_run(
        self,
        *,
        sync_run_id: int,
        status: str,
        contacts_fetched: int,
        contacts_written: int,
        contacts_deactivated: int,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET status = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    contacts_fetched = ?,
                    contacts_written = ?,
                    contacts_deactivated = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    contacts_fetched,
                    contacts_written,
                    contacts_deactivated,
                    error_message,
                    sync_run_id,
                ),
            )

    def empty_database(self) -> dict[str, int | bool]:
        with self._connect() as conn:
            counts_row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM contacts) AS contacts_deleted,
                    (SELECT COUNT(*) FROM contact_methods) AS methods_deleted,
                    (SELECT COUNT(*) FROM contact_aliases) AS aliases_deleted,
                    (SELECT COUNT(*) FROM sync_runs) AS sync_runs_deleted
                """
            ).fetchone()
            counts = dict(counts_row)

            conn.execute("DELETE FROM contacts")
            conn.execute("DELETE FROM sync_runs")
            conn.execute(
                """
                DELETE FROM sqlite_sequence
                WHERE name IN ('contacts', 'contact_methods', 'contact_aliases', 'sync_runs')
                """
            )

        counts["ids_reset"] = True
        return counts

    def vacuum(self) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute("VACUUM")

    def replace_contacts(
        self,
        *,
        source: str,
        source_account: str,
        contacts: Iterable[ContactRecord],
        sync_run_id: int,
    ) -> SyncStats:
        fetched_count = 0
        written_count = 0

        with self._connect() as conn:
            for contact in contacts:
                fetched_count += 1
                self._upsert_contact(conn, contact=contact, sync_run_id=sync_run_id)
                written_count += 1

            deactivate_cursor = conn.execute(
                """
                UPDATE contacts
                SET active = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE source = ?
                  AND source_account = ?
                  AND active = 1
                  AND COALESCE(last_seen_sync_id, 0) != ?
                """,
                (source, source_account, sync_run_id),
            )
            deactivated_count = int(deactivate_cursor.rowcount or 0)

        return SyncStats(
            fetched_count=fetched_count,
            written_count=written_count,
            deactivated_count=deactivated_count,
            sync_run_id=sync_run_id,
        )

    def list_contacts(
        self,
        *,
        query: str | None = None,
        include_inactive: bool = False,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT c.id,
                   c.source,
                   c.source_account,
                   c.source_contact_id,
                   c.display_name,
                   c.given_name,
                   c.family_name,
                   c.nickname,
                   c.organization,
                   c.notes,
                   c.active,
                   c.updated_at
            FROM contacts AS c
        """
        params: list[Any] = []
        conditions: list[str] = []

        if query:
            conditions.append(
                """
                (
                    c.display_name LIKE ?
                    OR COALESCE(c.given_name, '') LIKE ?
                    OR COALESCE(c.family_name, '') LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM contact_methods AS m
                        WHERE m.contact_id = c.id
                          AND (m.value LIKE ? OR COALESCE(m.normalized_value, '') LIKE ?)
                    )
                )
                """
            )
            like_query = f"%{query}%"
            params.extend([like_query, like_query, like_query, like_query, like_query])
        if source:
            conditions.append("c.source = ?")
            params.append(source)
        if not include_inactive:
            conditions.append("c.active = 1")

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY c.display_name COLLATE NOCASE"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_contact_summary(conn, row["id"], dict(row)) for row in rows]

    def list_source_summaries(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            source_rows = conn.execute(
                """
                SELECT source, source_account FROM contacts
                UNION
                SELECT source, source_account FROM sync_runs
                ORDER BY source, source_account
                """
            ).fetchall()

            summaries: list[dict[str, Any]] = []
            for source_row in source_rows:
                source = str(source_row["source"])
                source_account = str(source_row["source_account"])
                counts_row = conn.execute(
                    """
                    SELECT COUNT(*) AS total_contacts,
                           COALESCE(SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END), 0) AS active_contacts,
                           COALESCE(SUM(CASE WHEN active = 0 THEN 1 ELSE 0 END), 0) AS inactive_contacts
                    FROM contacts
                    WHERE source = ? AND source_account = ?
                    """,
                    (source, source_account),
                ).fetchone()
                last_run_row = conn.execute(
                    """
                    SELECT id,
                           status,
                           started_at,
                           completed_at,
                           contacts_fetched,
                           contacts_written,
                           contacts_deactivated,
                           error_message
                    FROM sync_runs
                    WHERE source = ? AND source_account = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (source, source_account),
                ).fetchone()
                summary = {
                    "source": source,
                    "source_account": source_account,
                    "total_contacts": int(counts_row["total_contacts"] or 0),
                    "active_contacts": int(counts_row["active_contacts"] or 0),
                    "inactive_contacts": int(counts_row["inactive_contacts"] or 0),
                    "last_run_id": int(last_run_row["id"]) if last_run_row is not None else None,
                    "last_run_status": str(last_run_row["status"]) if last_run_row is not None else None,
                    "last_run_started_at": str(last_run_row["started_at"]) if last_run_row is not None else None,
                    "last_run_completed_at": (
                        str(last_run_row["completed_at"]) if last_run_row is not None and last_run_row["completed_at"] else None
                    ),
                    "last_run_contacts_fetched": (
                        int(last_run_row["contacts_fetched"]) if last_run_row is not None else None
                    ),
                    "last_run_contacts_written": (
                        int(last_run_row["contacts_written"]) if last_run_row is not None else None
                    ),
                    "last_run_contacts_deactivated": (
                        int(last_run_row["contacts_deactivated"]) if last_run_row is not None else None
                    ),
                    "last_run_error_message": (
                        str(last_run_row["error_message"]) if last_run_row is not None and last_run_row["error_message"] else None
                    ),
                }
                summaries.append(self._attach_source_metadata(summary))
            return summaries

    def export_contacts(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        return self.list_contacts(include_inactive=include_inactive)

    def write_export_json(self, *, output_path: Path, include_inactive: bool = False) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.export_contacts(include_inactive=include_inactive)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def get_contact(self, *, contact_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT c.id,
                       c.source,
                       c.source_account,
                       c.source_contact_id,
                       c.display_name,
                       c.given_name,
                       c.family_name,
                       c.nickname,
                       c.organization,
                       c.notes,
                       c.active,
                       c.updated_at
                FROM contacts AS c
                WHERE c.id = ?
                """,
                (contact_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Contact {contact_id} not found")
            return self._row_to_contact_summary(conn, contact_id, dict(row))

    def get_contact_details(self, *, contact_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT c.id,
                       c.source,
                       c.source_account,
                       c.source_contact_id,
                       c.display_name,
                       c.given_name,
                       c.family_name,
                       c.nickname,
                       c.organization,
                       c.notes,
                       c.active,
                       c.last_seen_sync_id,
                       c.raw_json,
                       c.created_at,
                       c.updated_at
                FROM contacts AS c
                WHERE c.id = ?
                """,
                (contact_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Contact {contact_id} not found")
            return self._row_to_contact_details(conn, contact_id, dict(row))

    def add_alias(self, *, contact_id: int, alias_text: str) -> None:
        normalized_alias = normalize_person_name(alias_text)
        if not normalized_alias:
            raise ValueError("Alias text cannot be empty")

        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if exists is None:
                raise KeyError(f"Contact {contact_id} not found")
            conn.execute(
                """
                INSERT INTO contact_aliases (contact_id, alias_text, normalized_alias)
                VALUES (?, ?, ?)
                ON CONFLICT(contact_id, normalized_alias) DO UPDATE SET
                    alias_text = excluded.alias_text
                """,
                (contact_id, alias_text.strip(), normalized_alias),
            )

    def remove_alias(self, *, contact_id: int, alias_text: str) -> bool:
        normalized_alias = normalize_person_name(alias_text)
        if not normalized_alias:
            return False
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM contact_aliases
                WHERE contact_id = ? AND normalized_alias = ?
                """,
                (contact_id, normalized_alias),
            )
            return bool(cursor.rowcount)

    def list_aliases(self, *, contact_id: int | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT a.id,
                   a.contact_id,
                   c.display_name AS contact_name,
                   a.alias_text,
                   a.normalized_alias,
                   a.created_at
            FROM contact_aliases AS a
            JOIN contacts AS c ON c.id = a.contact_id
        """
        params: list[Any] = []
        if contact_id is not None:
            sql += " WHERE a.contact_id = ?"
            params.append(contact_id)
        sql += " ORDER BY c.display_name COLLATE NOCASE, a.alias_text COLLATE NOCASE"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def _upsert_contact(self, conn: sqlite3.Connection, *, contact: ContactRecord, sync_run_id: int) -> None:
        raw_json = json.dumps(contact.raw_payload, ensure_ascii=False, sort_keys=True)
        cursor = conn.execute(
            """
            INSERT INTO contacts (
                source,
                source_account,
                source_contact_id,
                display_name,
                given_name,
                family_name,
                nickname,
                organization,
                notes,
                active,
                last_seen_sync_id,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(source, source_account, source_contact_id) DO UPDATE SET
                display_name = excluded.display_name,
                given_name = excluded.given_name,
                family_name = excluded.family_name,
                nickname = excluded.nickname,
                organization = excluded.organization,
                notes = excluded.notes,
                active = 1,
                last_seen_sync_id = excluded.last_seen_sync_id,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                contact.source,
                contact.source_account,
                contact.source_contact_id,
                contact.display_name,
                contact.given_name,
                contact.family_name,
                contact.nickname,
                contact.organization,
                contact.notes,
                sync_run_id,
                raw_json,
            ),
        )
        contact_id = int(cursor.fetchone()["id"])
        conn.execute("DELETE FROM contact_methods WHERE contact_id = ?", (contact_id,))
        conn.executemany(
            """
            INSERT INTO contact_methods (
                contact_id,
                kind,
                label,
                value,
                normalized_value,
                is_primary
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    contact_id,
                    method.kind,
                    method.label,
                    method.value,
                    method.normalized_value,
                    int(method.is_primary),
                )
                for method in contact.methods
            ],
        )

    def _row_to_contact_summary(
        self,
        conn: sqlite3.Connection,
        contact_id: int,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        row["active"] = bool(row["active"])
        row["methods"] = self._fetch_contact_methods(conn, contact_id=contact_id)
        row["aliases"] = self._fetch_contact_aliases(conn, contact_id=contact_id)
        return self._attach_source_metadata(row)

    def _row_to_contact_details(
        self,
        conn: sqlite3.Connection,
        contact_id: int,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        raw_json_text = str(row.get("raw_json") or "")
        row["active"] = bool(row["active"])
        row["methods"] = self._fetch_contact_methods(conn, contact_id=contact_id, include_metadata=True)
        row["aliases"] = self._fetch_contact_aliases(conn, contact_id=contact_id)
        row["alias_records"] = self._fetch_contact_alias_records(conn, contact_id=contact_id)
        row["raw_json_text"] = raw_json_text
        try:
            row["raw_json"] = json.loads(raw_json_text)
        except json.JSONDecodeError:
            row["raw_json"] = raw_json_text
        return self._attach_source_metadata(row)

    def _fetch_contact_methods(
        self,
        conn: sqlite3.Connection,
        *,
        contact_id: int,
        include_metadata: bool = False,
    ) -> list[dict[str, Any]]:
        columns = "kind, label, value, normalized_value, is_primary"
        if include_metadata:
            columns = f"id, {columns}, created_at"
        rows = conn.execute(
            f"""
            SELECT {columns}
            FROM contact_methods
            WHERE contact_id = ?
            ORDER BY kind, is_primary DESC, value COLLATE NOCASE
            """,
            (contact_id,),
        ).fetchall()
        methods = [dict(row) for row in rows]
        for method in methods:
            method["is_primary"] = bool(method["is_primary"])
        return methods

    def _fetch_contact_aliases(
        self,
        conn: sqlite3.Connection,
        *,
        contact_id: int,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT alias_text
            FROM contact_aliases
            WHERE contact_id = ?
            ORDER BY alias_text COLLATE NOCASE
            """,
            (contact_id,),
        ).fetchall()
        return [str(alias["alias_text"]) for alias in rows]

    def _fetch_contact_alias_records(
        self,
        conn: sqlite3.Connection,
        *,
        contact_id: int,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, alias_text, normalized_alias, created_at
            FROM contact_aliases
            WHERE contact_id = ?
            ORDER BY alias_text COLLATE NOCASE
            """,
            (contact_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _attach_source_metadata(row: dict[str, Any]) -> dict[str, Any]:
        source = str(row.get("source") or "")
        source_account = str(row.get("source_account") or "")
        definition = get_contact_source_definition(source)
        row["source_label"] = definition.label
        row["source_family"] = definition.family
        row["source_behavior"] = definition.behavior
        row["source_syncable"] = definition.syncable
        row["source_display"] = build_source_display(source=source, source_account=source_account)
        return row

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
