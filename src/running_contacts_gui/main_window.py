from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from running_contacts.config import AppPaths, build_app_paths, get_app_paths
from running_contacts.contacts.storage import ContactsRepository
from running_contacts.matching.models import MatchReport, MatchResult
from running_contacts.matching.service import (
    export_selected_matches_csv,
    filter_and_sort_matches,
    match_dataset,
    select_matches,
)
from running_contacts.race_results.service import fetch_acn_results
from running_contacts.race_results.storage import RaceResultsRepository

from .state import GuiState, MatchingFilters
from .table_presenter import TablePresenter


DEFAULT_RESULTS_LIMIT = 100
STATUS_OPTIONS = ("accepted", "ambiguous", "all")
SORT_OPTIONS = ("position", "time", "athlete", "contact", "team", "score")


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        contacts_db_path: Path | None = None,
        results_db_path: Path | None = None,
        app_paths: AppPaths | None = None,
    ) -> None:
        super().__init__()
        self.app_paths = app_paths or self._resolve_app_paths(
            contacts_db_path=contacts_db_path,
            results_db_path=results_db_path,
        )
        self.contacts_db_path = Path(contacts_db_path or self.app_paths.contacts_db)
        self.results_db_path = Path(results_db_path or self.app_paths.race_results_db)
        self.state = GuiState()

        self.setWindowTitle("running_contacts")
        self.resize(1280, 760)

        self.contacts_query_input = QLineEdit()
        self.results_url_input = QLineEdit()
        self.results_dataset_input = QLineEdit()
        self.results_alias_input = QLineEdit()
        self.matching_dataset_input = QLineEdit()
        self.matching_team_input = QLineEdit()
        self.matching_name_query_input = QLineEdit()
        self.matching_category_input = QLineEdit()

        self.matching_status_combo = QComboBox()
        self.matching_status_combo.addItems(list(STATUS_OPTIONS))
        self.matching_sort_combo = QComboBox()
        self.matching_sort_combo.addItems(list(SORT_OPTIONS))
        self.matching_reviewed_only_checkbox = QCheckBox("Reviewed only")

        self.contacts_load_button = QPushButton("Load contacts")
        self.contacts_export_button = QPushButton("Export JSON")
        self.list_datasets_button = QPushButton("List datasets")
        self.show_results_button = QPushButton("Show results")
        self.fetch_acn_button = QPushButton("Fetch ACN")
        self.add_alias_button = QPushButton("Add alias")
        self.run_matching_button = QPushButton("Run matching")
        self.export_matches_button = QPushButton("Export CSV")

        self.table = QTableWidget()
        self.table.setObjectName("central_table")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.table_presenter = TablePresenter(self.table)

        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        controls_layout = QVBoxLayout()
        controls_layout.addWidget(self._build_contacts_section())
        controls_layout.addWidget(self._build_race_results_section())
        controls_layout.addWidget(self._build_matching_section())
        controls_layout.addStretch(1)

        layout.addLayout(controls_layout, stretch=0)
        layout.addWidget(self.table, stretch=1)
        self.setCentralWidget(central_widget)

        self.setStatusBar(QStatusBar(self))
        self.table_presenter.show_placeholder("No data loaded yet.")
        self.statusBar().showMessage("GUI ready.")

        self.contacts_load_button.clicked.connect(self.load_contacts)
        self.contacts_export_button.clicked.connect(self.export_contacts_json)
        self.list_datasets_button.clicked.connect(self.list_datasets)
        self.show_results_button.clicked.connect(self.show_results)
        self.fetch_acn_button.clicked.connect(self.fetch_acn_dataset)
        self.add_alias_button.clicked.connect(self.add_dataset_alias)
        self.run_matching_button.clicked.connect(self.run_matching)
        self.export_matches_button.clicked.connect(self.export_matches_csv)
        self.table.itemSelectionChanged.connect(self._handle_table_selection_changed)
        self.matching_status_combo.currentTextChanged.connect(self.apply_matching_filters)
        self.matching_sort_combo.currentTextChanged.connect(self.apply_matching_filters)
        self.matching_team_input.textChanged.connect(self.apply_matching_filters)
        self.matching_name_query_input.textChanged.connect(self.apply_matching_filters)
        self.matching_category_input.textChanged.connect(self.apply_matching_filters)
        self.matching_reviewed_only_checkbox.checkStateChanged.connect(self.apply_matching_filters)

    def _build_contacts_section(self) -> QGroupBox:
        section = QGroupBox("Contacts")
        section.setObjectName("contacts_section")
        layout = QVBoxLayout(section)

        self.contacts_query_input.setPlaceholderText("Search by name, email, or phone")
        layout.addWidget(self.contacts_query_input)
        layout.addWidget(self.contacts_load_button)
        layout.addWidget(self.contacts_export_button)
        return section

    def _build_race_results_section(self) -> QGroupBox:
        section = QGroupBox("Race Results")
        section.setObjectName("race_results_section")
        layout = QVBoxLayout(section)

        self.results_url_input.setPlaceholderText("ACN public URL")
        self.results_dataset_input.setPlaceholderText("Dataset id or alias")
        self.results_alias_input.setPlaceholderText("Alias for current dataset")
        layout.addWidget(QLabel("ACN URL"))
        layout.addWidget(self.results_url_input)
        layout.addWidget(self.fetch_acn_button)
        layout.addWidget(QLabel("Dataset"))
        layout.addWidget(self.results_dataset_input)
        layout.addWidget(self.list_datasets_button)
        layout.addWidget(self.show_results_button)
        layout.addWidget(QLabel("New alias"))
        layout.addWidget(self.results_alias_input)
        layout.addWidget(self.add_alias_button)
        return section

    def _build_matching_section(self) -> QGroupBox:
        section = QGroupBox("Matching")
        section.setObjectName("matching_section")
        layout = QVBoxLayout(section)

        self.matching_dataset_input.setPlaceholderText("Dataset id or alias")
        self.matching_team_input.setPlaceholderText("Filter by team")
        self.matching_name_query_input.setPlaceholderText("Filter by athlete or contact")
        self.matching_category_input.setPlaceholderText("Filter by category")
        layout.addWidget(QLabel("Dataset"))
        layout.addWidget(self.matching_dataset_input)
        layout.addWidget(QLabel("Status"))
        layout.addWidget(self.matching_status_combo)
        layout.addWidget(QLabel("Sort"))
        layout.addWidget(self.matching_sort_combo)
        layout.addWidget(self.matching_team_input)
        layout.addWidget(self.matching_name_query_input)
        layout.addWidget(self.matching_category_input)
        layout.addWidget(self.matching_reviewed_only_checkbox)
        layout.addWidget(self.run_matching_button)
        layout.addWidget(self.export_matches_button)
        return section

    def load_contacts(self) -> None:
        try:
            repository = ContactsRepository(self.contacts_db_path)
            repository.initialize()
            query = self._clean_text(self.contacts_query_input.text())
            contacts = repository.list_contacts(query=query)
            self.table_presenter.show_contacts(contacts)
            self.statusBar().showMessage(f"Loaded {len(contacts)} contacts.")
        except Exception as exc:
            self._show_error(exc)

    def export_contacts_json(self) -> None:
        try:
            repository = ContactsRepository(self.contacts_db_path)
            repository.initialize()
            output_path = self._choose_save_path(
                title="Export contacts JSON",
                default_path=self.state.last_export_path or self.app_paths.contacts_export_json,
                file_filter="JSON Files (*.json)",
            )
            if output_path is None:
                self.statusBar().showMessage("Export cancelled.")
                return
            export_path = repository.write_export_json(output_path=output_path)
            self.state.last_export_path = export_path
            self.statusBar().showMessage(f"Exported contacts to {export_path}.")
        except Exception as exc:
            self._show_error(exc)

    def list_datasets(self) -> None:
        try:
            repository = RaceResultsRepository(self.results_db_path)
            repository.initialize()
            datasets = repository.list_datasets()
            self.table_presenter.show_datasets(datasets)
            self.statusBar().showMessage(f"Loaded {len(datasets)} datasets.")
            self._select_dataset_row(self.state.last_dataset_id)
        except Exception as exc:
            self._show_error(exc)

    def show_results(self) -> None:
        try:
            selector = self._require_dataset_selector(self.results_dataset_input)
            repository = RaceResultsRepository(self.results_db_path)
            repository.initialize()
            dataset_id = repository.resolve_dataset_selector(selector)
            self._remember_current_dataset(selector=selector, dataset_id=dataset_id)
            results = repository.list_results(dataset_id=dataset_id, limit=DEFAULT_RESULTS_LIMIT)
            self.table_presenter.show_race_results(results)
            self.statusBar().showMessage(
                f"Showing {len(results)} results for dataset {dataset_id}."
            )
        except Exception as exc:
            self._show_error(exc)

    def fetch_acn_dataset(self) -> None:
        try:
            url = self._clean_text(self.results_url_input.text())
            if url is None:
                raise ValueError("Enter an ACN public URL first.")
            stats = fetch_acn_results(
                url=url,
                db_path=self.results_db_path,
                raw_dir=self.app_paths.raw_acn_dir,
            )
            repository = RaceResultsRepository(self.results_db_path)
            repository.initialize()
            datasets = repository.list_datasets()
            self._remember_current_dataset(selector=str(stats.dataset_id), dataset_id=stats.dataset_id)
            self._invalidate_matching_cache()
            self.results_dataset_input.setText(str(stats.dataset_id))
            self.matching_dataset_input.setText(str(stats.dataset_id))
            self.table_presenter.show_datasets(datasets)
            self._select_dataset_row(stats.dataset_id)
            self.statusBar().showMessage(
                f"Fetched ACN dataset {stats.dataset_id} with {stats.results_count} results. "
                f"Loaded {len(datasets)} datasets."
            )
        except Exception as exc:
            self._show_error(exc)

    def add_dataset_alias(self) -> None:
        try:
            alias_text = self._clean_text(self.results_alias_input.text())
            if alias_text is None:
                raise ValueError("Enter an alias first.")
            repository = RaceResultsRepository(self.results_db_path)
            repository.initialize()
            dataset_id = self._resolve_current_dataset_id(repository)
            repository.add_dataset_alias(dataset_id=dataset_id, alias_text=alias_text)
            datasets = repository.list_datasets()
            self._remember_current_dataset(selector=alias_text, dataset_id=dataset_id)
            self.results_dataset_input.setText(alias_text)
            self.matching_dataset_input.setText(alias_text)
            self.table_presenter.show_datasets(datasets)
            self._select_dataset_row(dataset_id)
            self.statusBar().showMessage(f"Added alias to dataset {dataset_id}: {alias_text}")
        except Exception as exc:
            self._show_error(exc)

    def run_matching(self) -> None:
        try:
            report = self._ensure_match_report()
            self._apply_matching_filters(report)
        except Exception as exc:
            self._show_error(exc)

    def export_matches_csv(self) -> None:
        try:
            report = self._ensure_match_report()
            matches = self._filtered_matches(report)
            output_path = self._choose_save_path(
                title="Export matches CSV",
                default_path=self.state.last_export_path or self.app_paths.matches_export_csv,
                file_filter="CSV Files (*.csv)",
            )
            if output_path is None:
                self.statusBar().showMessage("Export cancelled.")
                return
            export_path = export_selected_matches_csv(matches=matches, output_path=output_path)
            self.state.last_export_path = export_path
            self.statusBar().showMessage(f"Exported {len(matches)} matches to {export_path}.")
        except Exception as exc:
            self._show_error(exc)

    def apply_matching_filters(self, *_: object) -> None:
        report = self.state.last_match_report
        self.state.current_matching_filters = self._matching_filters_from_widgets()
        if report is None:
            return
        try:
            self._apply_matching_filters(report)
        except Exception as exc:
            self._show_error(exc)

    def _require_dataset_selector(self, field: QLineEdit) -> str:
        selector = self._clean_text(field.text())
        if selector is None:
            raise ValueError("Enter a dataset id or alias first.")
        return selector

    def _ensure_match_report(self) -> MatchReport:
        selector = self._require_dataset_selector(self.matching_dataset_input)
        repository = RaceResultsRepository(self.results_db_path)
        repository.initialize()
        dataset_id = repository.resolve_dataset_selector(selector)
        cached_selector = self.state.current_dataset_selector
        if (
            self.state.last_match_report is not None
            and self.state.last_dataset_id == dataset_id
            and cached_selector == selector
        ):
            return self.state.last_match_report
        report = match_dataset(
            contacts_db_path=self.contacts_db_path,
            results_db_path=self.results_db_path,
            dataset_id=dataset_id,
        )
        self._remember_current_dataset(selector=selector, dataset_id=dataset_id)
        self.state.last_match_report = report
        return report

    def _apply_matching_filters(self, report: MatchReport) -> None:
        self.state.current_matching_filters = self._matching_filters_from_widgets()
        matches = self._filtered_matches(report)
        self.table_presenter.show_filtered_matches(matches)
        self.statusBar().showMessage(
            f"Showing {len(matches)} matching rows. "
            f"{len(report.accepted_matches)} accepted, "
            f"{len(report.ambiguous_matches)} ambiguous, "
            f"{report.unmatched_count} unmatched."
        )

    def _filtered_matches(self, report: MatchReport) -> list[MatchResult]:
        filters = self.state.current_matching_filters
        matches = select_matches(report, status=filters.status)
        return filter_and_sort_matches(
            matches,
            name_query=filters.name_query,
            team=filters.team,
            category=filters.category,
            reviewed_only=filters.reviewed_only,
            sort_by=filters.sort_by,
        )

    def _matching_filters_from_widgets(self) -> MatchingFilters:
        return MatchingFilters(
            status=self.matching_status_combo.currentText(),
            sort_by=self.matching_sort_combo.currentText(),
            team=self._clean_text(self.matching_team_input.text()),
            name_query=self._clean_text(self.matching_name_query_input.text()),
            category=self._clean_text(self.matching_category_input.text()),
            reviewed_only=self.matching_reviewed_only_checkbox.isChecked(),
        )

    def _resolve_current_dataset_id(self, repository: RaceResultsRepository) -> int:
        metadata = self.table_presenter.current_row_metadata()
        if metadata and metadata.get("dataset_id") is not None:
            return int(metadata["dataset_id"])
        selector = self._clean_text(self.results_dataset_input.text())
        if selector is not None:
            return repository.resolve_dataset_selector(selector)
        if self.state.last_dataset_id is not None:
            return self.state.last_dataset_id
        selector = self._clean_text(self.matching_dataset_input.text())
        if selector is not None:
            return repository.resolve_dataset_selector(selector)
        raise ValueError("Select or enter a dataset first.")

    def _handle_table_selection_changed(self) -> None:
        metadata = self.table_presenter.current_row_metadata()
        if not metadata:
            return
        dataset_id = metadata.get("dataset_id")
        if dataset_id is None:
            return
        self.state.last_dataset_id = int(dataset_id)
        if self.table_presenter.current_view_name == "datasets":
            dataset_text = str(dataset_id)
            if not self.results_dataset_input.text().strip():
                self.results_dataset_input.setText(dataset_text)
            if not self.matching_dataset_input.text().strip():
                self.matching_dataset_input.setText(dataset_text)

    def _select_dataset_row(self, dataset_id: int | None) -> None:
        if dataset_id is None:
            return
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is None:
                continue
            metadata = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(metadata, dict) and metadata.get("dataset_id") == dataset_id:
                self.table.selectRow(row_index)
                return

    def _remember_current_dataset(self, *, selector: str, dataset_id: int) -> None:
        self.state.current_dataset_selector = selector
        self.state.last_dataset_id = dataset_id

    def _invalidate_matching_cache(self) -> None:
        self.state.last_match_report = None

    @staticmethod
    def _resolve_app_paths(
        *,
        contacts_db_path: Path | None,
        results_db_path: Path | None,
    ) -> AppPaths:
        if contacts_db_path is None and results_db_path is None:
            return get_app_paths()
        return build_app_paths(
            data_dir=MainWindow._infer_data_dir(
                contacts_db_path=contacts_db_path,
                results_db_path=results_db_path,
            )
        )

    @staticmethod
    def _infer_data_dir(
        *,
        contacts_db_path: Path | None,
        results_db_path: Path | None,
    ) -> Path:
        candidates = [path.parent for path in [contacts_db_path, results_db_path] if path is not None]
        if not candidates:
            return Path.cwd() / "data"
        if len(candidates) == 2 and candidates[0] == candidates[1]:
            return candidates[0]
        return candidates[0]

    def _choose_save_path(self, *, title: str, default_path: Path, file_filter: str) -> Path | None:
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            title,
            str(default_path),
            file_filter,
        )
        if not selected_path:
            return None
        return Path(selected_path)

    @staticmethod
    def _clean_text(value: str) -> str | None:
        cleaned = value.strip()
        return cleaned or None

    def _show_error(self, exc: Exception) -> None:
        self.statusBar().showMessage(f"Error: {exc}")
