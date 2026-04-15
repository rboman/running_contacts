from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from match_my_contacts.matching.models import MatchReport, MatchResult


@dataclass(slots=True, frozen=True)
class TableRow:
    cells: tuple[str, ...]
    metadata: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class TableView:
    name: str
    headers: tuple[str, ...]
    rows: tuple[TableRow, ...]
    initial_widths: tuple[int, ...] | None = None
    stretch_column: int | None = None


@dataclass(slots=True, frozen=True)
class ContactColumnDefinition:
    key: str
    header: str
    width: int
    default_visible: bool = True
    stretch: bool = False


class TablePresenter:
    """Centralize all table transformations and QTableWidget population."""

    CONTACT_COLUMNS: tuple[ContactColumnDefinition, ...] = (
        ContactColumnDefinition("id", "id", 60),
        ContactColumnDefinition("display_name", "display_name", 180),
        ContactColumnDefinition("source", "source", 190, default_visible=False),
        ContactColumnDefinition("email", "email", 220),
        ContactColumnDefinition("phone", "phone", 150),
        ContactColumnDefinition("organization", "organization", 180),
        ContactColumnDefinition("aliases", "aliases", 180),
        ContactColumnDefinition("notes", "notes", 260, stretch=True),
    )

    def __init__(self, table: QTableWidget) -> None:
        self.table = table
        self._current_view_name = "placeholder"

    def show_placeholder(self, message: str) -> None:
        self._render(
            TableView(
                name="placeholder",
                headers=("message",),
                rows=(TableRow(cells=(message,), metadata={"view": "placeholder"}),),
                stretch_column=0,
            )
        )

    def show_contacts(
        self,
        contacts: list[dict[str, Any]],
        *,
        visible_column_ids: list[str] | None = None,
    ) -> None:
        columns = self._resolve_contact_columns(visible_column_ids)
        rows = tuple(
            TableRow(
                cells=tuple(self._contact_cell_values(contact, columns)),
                metadata={"view": "contacts", "contact_id": int(contact["id"])},
            )
            for contact in contacts
        )
        self._render(
            TableView(
                name="contacts",
                headers=tuple(column.header for column in columns),
                rows=rows,
                initial_widths=tuple(column.width for column in columns),
                stretch_column=self._stretch_column_index(columns),
            )
        )

    def show_datasets(self, datasets: list[dict[str, Any]]) -> None:
        rows = tuple(
            TableRow(
                cells=self._dataset_row(dataset),
                metadata={"view": "datasets", "dataset_id": int(dataset["id"])},
            )
            for dataset in datasets
        )
        self._render(
            TableView(
                name="datasets",
                headers=("id", "event_title", "event_date", "event_location", "report", "aliases", "rows"),
                rows=rows,
                initial_widths=(60, 240, 110, 160, 140, 180, 80),
                stretch_column=1,
            )
        )

    def show_race_results(self, results: list[dict[str, Any]]) -> None:
        rows = tuple(
            TableRow(
                cells=self._race_result_row(result),
                metadata={
                    "view": "race_results",
                    "dataset_id": int(result["dataset_id"]),
                    "result_id": int(result["id"]),
                },
            )
            for result in results
        )
        self._render(
            TableView(
                name="race_results",
                headers=("id", "position", "athlete_name", "finish_time", "team", "bib", "category"),
                rows=rows,
                initial_widths=(60, 80, 220, 120, 180, 90, 100),
                stretch_column=4,
            )
        )

    def show_accepted_matches(self, report: MatchReport) -> None:
        self._render_match_rows(name="accepted_matches", matches=report.accepted_matches)

    def show_filtered_matches(self, matches: list[MatchResult]) -> None:
        self._render_match_rows(name="filtered_matches", matches=matches)

    def show_match_reviews(self, reviews: list[dict[str, Any]]) -> None:
        rows = tuple(
            TableRow(
                cells=self._review_row(review),
                metadata={
                    "view": "match_reviews",
                    "dataset_id": int(review["dataset_id"]),
                    "result_id": int(review["result_id"]),
                },
            )
            for review in reviews
        )
        self._render(
            TableView(
                name="match_reviews",
                headers=(
                    "result_id",
                    "status",
                    "athlete_name",
                    "contact_id",
                    "note",
                    "updated_at",
                ),
                rows=rows,
                initial_widths=(90, 100, 220, 100, 220, 160),
                stretch_column=4,
            )
        )

    def current_row_metadata(self) -> dict[str, Any] | None:
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        first_item = self.table.item(current_row, 0)
        if first_item is None:
            return None
        metadata = first_item.data(Qt.ItemDataRole.UserRole)
        return metadata if isinstance(metadata, dict) else None

    @property
    def current_view_name(self) -> str:
        return self._current_view_name

    @classmethod
    def contact_columns(cls) -> tuple[ContactColumnDefinition, ...]:
        return cls.CONTACT_COLUMNS

    def _render(self, view: TableView) -> None:
        self._current_view_name = view.name
        header = self.table.horizontalHeader()
        self.table.clear()
        self.table.setColumnCount(len(view.headers))
        self.table.setHorizontalHeaderLabels(list(view.headers))
        self.table.setRowCount(len(view.rows))
        header.setStretchLastSection(False)

        for row_index, row in enumerate(view.rows):
            for column_index, value in enumerate(row.cells):
                item = QTableWidgetItem(value)
                if value:
                    item.setToolTip(value)
                if column_index == 0 and row.metadata is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row.metadata)
                self.table.setItem(row_index, column_index, item)

        self._apply_initial_layout(view)

    def _apply_initial_layout(self, view: TableView) -> None:
        header = self.table.horizontalHeader()
        widths = view.initial_widths or ()

        for column_index in range(self.table.columnCount()):
            if view.stretch_column == column_index:
                header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Stretch)
                continue

            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Interactive)
            if column_index < len(widths):
                self.table.setColumnWidth(column_index, widths[column_index])

    def _render_match_rows(self, *, name: str, matches: list[MatchResult]) -> None:
        rows = tuple(
            TableRow(
                cells=self._match_row(match),
                metadata={
                    "view": name,
                    "dataset_id": match.dataset_id,
                    "result_id": match.result_id,
                    "contact_id": match.contact_id,
                    "status": match.status,
                },
            )
            for match in matches
        )
        self._render(
            TableView(
                name=name,
                headers=(
                    "result_id",
                    "status",
                    "athlete_name",
                    "contact_name",
                    "match_method",
                    "score",
                    "position",
                    "finish_time",
                    "team",
                    "matched_alias",
                ),
                rows=rows,
                initial_widths=(90, 100, 220, 220, 120, 80, 80, 120, 180, 200),
                stretch_column=8,
            )
        )

    @staticmethod
    def _contact_data(contact: dict[str, Any]) -> dict[str, str]:
        email_values = [
            str(method["value"])
            for method in contact.get("methods", [])
            if method.get("kind") == "email" and method.get("value")
        ]
        phone_values = [
            str(method["value"])
            for method in contact.get("methods", [])
            if method.get("kind") == "phone" and method.get("value")
        ]
        aliases = ", ".join(str(alias) for alias in contact.get("aliases", []))
        notes = str(contact.get("notes", "") or "").replace("\n", " ").strip()
        return {
            "id": str(contact.get("id", "")),
            "display_name": str(contact.get("display_name", "")),
            "source": str(contact.get("source_display", "") or ""),
            "email": ", ".join(email_values),
            "phone": ", ".join(phone_values),
            "organization": str(contact.get("organization", "") or ""),
            "aliases": aliases,
            "notes": notes,
        }

    @staticmethod
    def _dataset_row(dataset: dict[str, Any]) -> tuple[str, ...]:
        aliases = ", ".join(str(alias) for alias in dataset.get("aliases", []))
        report = f"{dataset.get('context_db', '')}/{dataset.get('report_key', '')}".strip("/")
        return (
            str(dataset.get("id", "")),
            str(dataset.get("event_title", "") or ""),
            str(dataset.get("event_date", "") or ""),
            str(dataset.get("event_location", "") or ""),
            report,
            aliases,
            str(dataset.get("total_results", "") or ""),
        )

    @staticmethod
    def _race_result_row(result: dict[str, Any]) -> tuple[str, ...]:
        return (
            str(result.get("id", "")),
            str(result.get("position_text", "") or ""),
            str(result.get("athlete_name", "") or ""),
            str(result.get("finish_time", "") or ""),
            str(result.get("team", "") or ""),
            str(result.get("bib", "") or ""),
            str(result.get("category", "") or ""),
        )

    @staticmethod
    def _match_row(match: MatchResult) -> tuple[str, ...]:
        return (
            str(match.result_id),
            match.status,
            match.athlete_name,
            match.contact_name or "",
            match.match_method,
            f"{match.score:.1f}",
            match.position_text or "",
            match.finish_time or "",
            match.team or "",
            match.matched_alias or "",
        )

    @staticmethod
    def _review_row(review: dict[str, Any]) -> tuple[str, ...]:
        return (
            str(review.get("result_id", "")),
            str(review.get("status", "") or ""),
            str(review.get("athlete_name", "") or ""),
            str(review.get("contact_id", "") or ""),
            str(review.get("note", "") or ""),
            str(review.get("updated_at", "") or ""),
        )

    @classmethod
    def _resolve_contact_columns(
        cls,
        visible_column_ids: list[str] | None,
    ) -> tuple[ContactColumnDefinition, ...]:
        if not visible_column_ids:
            return tuple(column for column in cls.CONTACT_COLUMNS if column.default_visible)
        selected = set(visible_column_ids)
        resolved = tuple(column for column in cls.CONTACT_COLUMNS if column.key in selected)
        if resolved:
            return resolved
        return tuple(column for column in cls.CONTACT_COLUMNS if column.default_visible)

    @classmethod
    def _stretch_column_index(cls, columns: tuple[ContactColumnDefinition, ...]) -> int | None:
        for index, column in enumerate(columns):
            if column.stretch:
                return index
        return None

    @classmethod
    def _contact_cell_values(
        cls,
        contact: dict[str, Any],
        columns: tuple[ContactColumnDefinition, ...],
    ) -> tuple[str, ...]:
        contact_data = cls._contact_data(contact)
        return tuple(contact_data.get(column.key, "") for column in columns)
