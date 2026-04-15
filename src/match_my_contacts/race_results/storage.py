from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from match_my_contacts.matching.normalization import normalize_person_name

from .models import RaceDataset, RaceResultRow


class RaceResultsRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS race_datasets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    external_event_id TEXT NOT NULL,
                    context_db TEXT NOT NULL,
                    report_key TEXT NOT NULL,
                    report_path TEXT NOT NULL,
                    event_title TEXT,
                    event_date TEXT,
                    event_location TEXT,
                    event_country TEXT,
                    total_results INTEGER NOT NULL DEFAULT 0,
                    raw_event_path TEXT,
                    raw_results_path TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, context_db, report_key)
                );

                CREATE TABLE IF NOT EXISTS race_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    group_name TEXT,
                    group_rank INTEGER NOT NULL,
                    position_text TEXT,
                    bib TEXT,
                    athlete_name TEXT NOT NULL,
                    team TEXT,
                    country TEXT,
                    gender TEXT,
                    location TEXT,
                    finish_time TEXT,
                    pace_text TEXT,
                    category_rank TEXT,
                    category TEXT,
                    detail_token TEXT,
                    row_class TEXT,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(dataset_id) REFERENCES race_datasets(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_race_results_dataset_id ON race_results(dataset_id);
                CREATE INDEX IF NOT EXISTS idx_race_results_athlete_name ON race_results(athlete_name);

                CREATE TABLE IF NOT EXISTS race_dataset_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    alias_text TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(normalized_alias),
                    FOREIGN KEY(dataset_id) REFERENCES race_datasets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS matching_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    result_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('accepted', 'rejected')),
                    contact_id INTEGER,
                    note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(dataset_id, result_id),
                    FOREIGN KEY(dataset_id) REFERENCES race_datasets(id) ON DELETE CASCADE,
                    FOREIGN KEY(result_id) REFERENCES race_results(id) ON DELETE CASCADE
                );
                """
            )

    def save_dataset(self, *, dataset: RaceDataset, results: list[RaceResultRow]) -> int:
        metadata_json = json.dumps(dataset.metadata, ensure_ascii=False, sort_keys=True)

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO race_datasets (
                    provider,
                    source_url,
                    external_event_id,
                    context_db,
                    report_key,
                    report_path,
                    event_title,
                    event_date,
                    event_location,
                    event_country,
                    total_results,
                    raw_event_path,
                    raw_results_path,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, context_db, report_key) DO UPDATE SET
                    source_url = excluded.source_url,
                    external_event_id = excluded.external_event_id,
                    report_path = excluded.report_path,
                    event_title = excluded.event_title,
                    event_date = excluded.event_date,
                    event_location = excluded.event_location,
                    event_country = excluded.event_country,
                    total_results = excluded.total_results,
                    raw_event_path = excluded.raw_event_path,
                    raw_results_path = excluded.raw_results_path,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (
                    dataset.provider,
                    dataset.source_url,
                    dataset.external_event_id,
                    dataset.context_db,
                    dataset.report_key,
                    dataset.report_path,
                    dataset.event_title,
                    dataset.event_date,
                    dataset.event_location,
                    dataset.event_country,
                    dataset.total_results,
                    dataset.raw_event_path,
                    dataset.raw_results_path,
                    metadata_json,
                ),
            )
            dataset_id = int(cursor.fetchone()["id"])
            conn.execute("DELETE FROM race_results WHERE dataset_id = ?", (dataset_id,))
            conn.executemany(
                """
                INSERT INTO race_results (
                    dataset_id,
                    group_name,
                    group_rank,
                    position_text,
                    bib,
                    athlete_name,
                    team,
                    country,
                    gender,
                    location,
                    finish_time,
                    pace_text,
                    category_rank,
                    category,
                    detail_token,
                    row_class,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        dataset_id,
                        result.group_name,
                        result.group_rank,
                        result.position_text,
                        result.bib,
                        result.athlete_name,
                        result.team,
                        result.country,
                        result.gender,
                        result.location,
                        result.finish_time,
                        result.pace_text,
                        result.category_rank,
                        result.category,
                        result.detail_token,
                        result.row_class,
                        json.dumps(result.raw_row, ensure_ascii=False),
                    )
                    for result in results
                ],
            )
            return dataset_id

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       provider,
                       event_title,
                       event_date,
                       event_location,
                       context_db,
                       report_key,
                       total_results,
                       updated_at
                FROM race_datasets
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
            datasets = [dict(row) for row in rows]
            for dataset in datasets:
                dataset["aliases"] = self._fetch_dataset_aliases(conn, dataset_id=int(dataset["id"]))
            return datasets

    def resolve_dataset_selector(self, selector: str) -> int:
        normalized_selector = normalize_person_name(selector)
        with self._connect() as conn:
            if selector.isdigit():
                row = conn.execute(
                    "SELECT id FROM race_datasets WHERE id = ?",
                    (int(selector),),
                ).fetchone()
                if row is not None:
                    return int(row["id"])

            row = conn.execute(
                """
                SELECT dataset_id
                FROM race_dataset_aliases
                WHERE normalized_alias = ?
                """,
                (normalized_selector,),
            ).fetchone()
            if row is not None:
                return int(row["dataset_id"])

        raise KeyError(f"Dataset selector '{selector}' not found")

    def add_dataset_alias(self, *, dataset_id: int, alias_text: str) -> None:
        normalized_alias = normalize_person_name(alias_text)
        if not normalized_alias:
            raise ValueError("Dataset alias cannot be empty")

        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM race_datasets WHERE id = ?", (dataset_id,)).fetchone()
            if exists is None:
                raise KeyError(f"Dataset {dataset_id} not found")
            conn.execute(
                """
                INSERT INTO race_dataset_aliases (dataset_id, alias_text, normalized_alias)
                VALUES (?, ?, ?)
                ON CONFLICT(normalized_alias) DO UPDATE SET
                    dataset_id = excluded.dataset_id,
                    alias_text = excluded.alias_text
                """,
                (dataset_id, alias_text.strip(), normalized_alias),
            )

    def remove_dataset_alias(self, *, alias_text: str) -> bool:
        normalized_alias = normalize_person_name(alias_text)
        if not normalized_alias:
            return False
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM race_dataset_aliases
                WHERE normalized_alias = ?
                """,
                (normalized_alias,),
            )
            return bool(cursor.rowcount)

    def list_dataset_aliases(self, *, dataset_id: int | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT a.id,
                   a.dataset_id,
                   d.event_title,
                   d.event_date,
                   a.alias_text,
                   a.normalized_alias,
                   a.created_at
            FROM race_dataset_aliases AS a
            JOIN race_datasets AS d ON d.id = a.dataset_id
        """
        params: list[Any] = []
        if dataset_id is not None:
            sql += " WHERE a.dataset_id = ?"
            params.append(dataset_id)
        sql += " ORDER BY d.event_date DESC, d.event_title COLLATE NOCASE, a.alias_text COLLATE NOCASE"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def get_dataset(self, *, dataset_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id,
                       provider,
                       source_url,
                       external_event_id,
                       context_db,
                       report_key,
                       report_path,
                       event_title,
                       event_date,
                       event_location,
                       event_country,
                       total_results,
                       raw_event_path,
                       raw_results_path,
                       metadata_json,
                       updated_at
                FROM race_datasets
                WHERE id = ?
                """,
                (dataset_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Dataset {dataset_id} not found")

        payload = dict(row)
        payload["metadata"] = json.loads(payload.pop("metadata_json"))
        with self._connect() as conn:
            payload["aliases"] = self._fetch_dataset_aliases(conn, dataset_id=dataset_id)
        return payload

    def list_results(
        self,
        *,
        dataset_id: int,
        query: str | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT id,
                   dataset_id,
                   position_text,
                   bib,
                   athlete_name,
                   team,
                   country,
                   gender,
                   location,
                   finish_time,
                   pace_text,
                   category_rank,
                   category,
                   detail_token
            FROM race_results
            WHERE dataset_id = ?
        """
        params: list[Any] = [dataset_id]

        if query:
            sql += """
                AND (
                    athlete_name LIKE ?
                    OR COALESCE(team, '') LIKE ?
                    OR COALESCE(bib, '') LIKE ?
                )
            """
            like_query = f"%{query}%"
            params.extend([like_query, like_query, like_query])

        sql += " ORDER BY id"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def set_match_review(
        self,
        *,
        dataset_id: int,
        result_id: int,
        status: str,
        contact_id: int | None = None,
        note: str | None = None,
    ) -> None:
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM race_results WHERE id = ? AND dataset_id = ?",
                (result_id, dataset_id),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Result {result_id} not found in dataset {dataset_id}")
            conn.execute(
                """
                INSERT INTO matching_reviews (dataset_id, result_id, status, contact_id, note)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, result_id) DO UPDATE SET
                    status = excluded.status,
                    contact_id = excluded.contact_id,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (dataset_id, result_id, status, contact_id, note),
            )

    def clear_match_review(self, *, dataset_id: int, result_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM matching_reviews
                WHERE dataset_id = ? AND result_id = ?
                """,
                (dataset_id, result_id),
            )
            return bool(cursor.rowcount)

    def clear_all_match_reviews(self) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM matching_reviews")
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'matching_reviews'")
            return int(cursor.rowcount or 0)

    def list_match_reviews(self, *, dataset_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT mr.id,
                       mr.dataset_id,
                       mr.result_id,
                       rr.athlete_name,
                       mr.status,
                       mr.contact_id,
                       mr.note,
                       mr.created_at,
                       mr.updated_at
                FROM matching_reviews AS mr
                JOIN race_results AS rr ON rr.id = mr.result_id
                WHERE mr.dataset_id = ?
                ORDER BY rr.athlete_name COLLATE NOCASE
                """,
                (dataset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_match_reviews_map(self, *, dataset_id: int) -> dict[int, dict[str, Any]]:
        reviews = self.list_match_reviews(dataset_id=dataset_id)
        return {int(review["result_id"]): review for review in reviews}

    def export_dataset(self, *, dataset_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            dataset = conn.execute(
                """
                SELECT *
                FROM race_datasets
                WHERE id = ?
                """,
                (dataset_id,),
            ).fetchone()
            if dataset is None:
                raise KeyError(f"Dataset {dataset_id} not found")

            results = conn.execute(
                """
                SELECT position_text,
                       bib,
                       athlete_name,
                       team,
                       country,
                       gender,
                       location,
                       finish_time,
                       pace_text,
                       category_rank,
                       category,
                       detail_token
                FROM race_results
                WHERE dataset_id = ?
                ORDER BY id
                """,
                (dataset_id,),
            ).fetchall()

        payload = dict(dataset)
        payload["metadata"] = json.loads(payload.pop("metadata_json"))
        payload["results"] = [dict(row) for row in results]
        return payload

    def write_export_json(self, *, dataset_id: int, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.export_dataset(dataset_id=dataset_id)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _fetch_dataset_aliases(self, conn: sqlite3.Connection, *, dataset_id: int) -> list[str]:
        rows = conn.execute(
            """
            SELECT alias_text
            FROM race_dataset_aliases
            WHERE dataset_id = ?
            ORDER BY alias_text COLLATE NOCASE
            """,
            (dataset_id,),
        ).fetchall()
        return [str(row["alias_text"]) for row in rows]
