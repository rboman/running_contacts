from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from match_my_contacts.config import (
    AppPaths,
    build_app_paths,
    default_credentials_path,
    get_app_paths,
    write_app_paths,
)
from match_my_contacts.contacts.storage import ContactsRepository
from match_my_contacts.contacts.service import import_google_contacts_csv
from match_my_contacts.contacts.service import (
    ensure_google_credentials_file,
    resolve_google_sync_paths,
    sync_google_contacts,
)
from match_my_contacts.matching.models import MatchReport, MatchResult
from match_my_contacts.matching.service import (
    export_selected_matches_csv,
    filter_and_sort_matches,
    match_dataset,
    select_matches,
)
from match_my_contacts.race_results.service import fetch_acn_results
from match_my_contacts.race_results.storage import RaceResultsRepository

from .state import GuiState, MatchingFilters
from .contact_details_dialog import ContactDetailsDialog
from .config_dialog import ConfigDialog
from .contacts_columns_dialog import ContactsColumnsDialog
from .icons import apply_action_icon, apply_button_icon, apply_window_icon
from .table_presenter import TablePresenter


DEFAULT_RESULTS_LIMIT = 100
STATUS_OPTIONS = ("accepted", "ambiguous", "all")
SORT_OPTIONS = ("position", "time", "athlete", "contact", "team", "score")
CONTACT_COLUMNS_SETTINGS_KEY = "contacts/visible_columns"
SETTINGS_ORGANIZATION = "match-my-contacts"
SETTINGS_APPLICATION = "match-my-contacts-gui"


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        contacts_db_path: Path | None = None,
        results_db_path: Path | None = None,
        app_paths: AppPaths | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.app_paths = app_paths or self._resolve_app_paths(
            contacts_db_path=contacts_db_path,
            results_db_path=results_db_path,
        )
        self.contacts_db_path = Path(contacts_db_path or self.app_paths.contacts_db)
        self.results_db_path = Path(results_db_path or self.app_paths.race_results_db)
        self.settings = settings or QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        self.state = GuiState()
        self.visible_contact_column_ids = self._load_visible_contact_column_ids()

        self.setWindowTitle("match-my-contacts")
        self.resize(1280, 760)
        apply_window_icon(self)
        self._build_menu()

        self.contacts_query_input = QLineEdit()
        self.results_url_input = QLineEdit()
        self.results_dataset_input = QLineEdit()
        self.results_alias_input = QLineEdit()
        self.matching_dataset_input = QLineEdit()
        self.matching_team_input = QLineEdit()
        self.matching_name_query_input = QLineEdit()
        self.matching_category_input = QLineEdit()
        self.config_path_display = QLineEdit()
        self.data_dir_display = QLineEdit()
        self.credentials_path_display = QLineEdit()

        self.matching_status_combo = QComboBox()
        self.matching_status_combo.addItems(list(STATUS_OPTIONS))
        self.matching_sort_combo = QComboBox()
        self.matching_sort_combo.addItems(list(SORT_OPTIONS))
        self.matching_reviewed_only_checkbox = QCheckBox("Reviewed only")

        self.contacts_load_button = QPushButton("Load contacts")
        self.contacts_sync_button = QPushButton("Sync Google")
        self.contacts_import_button = QPushButton("Import Google CSV")
        self.contacts_export_button = QPushButton("Export JSON")
        self.contacts_columns_button = QPushButton("Columns...")
        self.list_datasets_button = QPushButton("List datasets")
        self.show_results_button = QPushButton("Show results")
        self.fetch_acn_button = QPushButton("Fetch ACN")
        self.add_alias_button = QPushButton("Add alias")
        self.run_matching_button = QPushButton("Run matching")
        self.export_matches_button = QPushButton("Export CSV")
        self.edit_config_button = QPushButton("Edit config")
        self.reload_config_button = QPushButton("Reload config")

        self.table = QTableWidget()
        self.table.setObjectName("central_table")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.controls_tabs = QTabWidget()
        self.controls_tabs.setObjectName("controls_tabs")
        self.controls_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.controls_tabs.setMinimumWidth(340)

        self.table_presenter = TablePresenter(self.table)
        self._apply_icons()
        self._apply_tooltips()

        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        self.controls_tabs.addTab(self._build_contacts_tab(), "Contacts")
        self.controls_tabs.addTab(self._build_race_results_tab(), "Race Results")
        self.controls_tabs.addTab(self._build_matching_tab(), "Matching")
        self.controls_tabs.addTab(self._build_config_tab(), "Config")
        self.controls_tabs.setTabToolTip(0, "Browse, import, export, and inspect local contacts.")
        self.controls_tabs.setTabToolTip(1, "Fetch races, list datasets, and inspect stored race results.")
        self.controls_tabs.setTabToolTip(2, "Run matching and filter the visible match rows.")
        self.controls_tabs.setTabToolTip(3, "Inspect and edit local application paths.")

        layout.addWidget(self.controls_tabs, stretch=0)
        layout.addWidget(self.table, stretch=1)
        self.setCentralWidget(central_widget)

        self.setStatusBar(QStatusBar(self))
        self.table_presenter.show_placeholder("No data loaded yet.")
        self.statusBar().showMessage("GUI ready.")

        self.contacts_load_button.clicked.connect(self.load_contacts)
        self.contacts_sync_button.clicked.connect(self.sync_google_contacts)
        self.contacts_import_button.clicked.connect(self.import_contacts_csv)
        self.contacts_export_button.clicked.connect(self.export_contacts_json)
        self.contacts_columns_button.clicked.connect(self.edit_contact_columns)
        self.list_datasets_button.clicked.connect(self.list_datasets)
        self.show_results_button.clicked.connect(self.show_results)
        self.fetch_acn_button.clicked.connect(self.fetch_acn_dataset)
        self.add_alias_button.clicked.connect(self.add_dataset_alias)
        self.run_matching_button.clicked.connect(self.run_matching)
        self.export_matches_button.clicked.connect(self.export_matches_csv)
        self.edit_config_button.clicked.connect(self.edit_config)
        self.reload_config_button.clicked.connect(self.reload_config)
        self.table.itemSelectionChanged.connect(self._handle_table_selection_changed)
        self.table.itemDoubleClicked.connect(self._handle_table_item_double_clicked)
        self.matching_status_combo.currentTextChanged.connect(self.apply_matching_filters)
        self.matching_sort_combo.currentTextChanged.connect(self.apply_matching_filters)
        self.matching_team_input.textChanged.connect(self.apply_matching_filters)
        self.matching_name_query_input.textChanged.connect(self.apply_matching_filters)
        self.matching_category_input.textChanged.connect(self.apply_matching_filters)
        self.matching_reviewed_only_checkbox.checkStateChanged.connect(self.apply_matching_filters)
        self._refresh_config_summary()
        self._auto_load_contacts_on_startup()

    def _build_contacts_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(self._build_contacts_section())
        page_layout.addStretch(1)
        return page

    def _build_contacts_section(self) -> QGroupBox:
        section = QGroupBox("Contacts")
        section.setObjectName("contacts_section")
        layout = QVBoxLayout(section)

        self.contacts_query_input.setPlaceholderText("Search by name, email, or phone")
        layout.addWidget(self.contacts_query_input)
        layout.addWidget(self.contacts_load_button)
        layout.addWidget(self.contacts_sync_button)
        layout.addWidget(self.contacts_import_button)
        layout.addWidget(self.contacts_export_button)
        layout.addWidget(self.contacts_columns_button)
        return section

    def _build_race_results_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(self._build_race_results_section())
        page_layout.addStretch(1)
        return page

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

    def _build_matching_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(self._build_matching_section())
        page_layout.addStretch(1)
        return page

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

    def _build_config_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(self._build_config_section())
        page_layout.addStretch(1)
        return page

    def _build_config_section(self) -> QGroupBox:
        section = QGroupBox("Config")
        section.setObjectName("config_section")
        layout = QVBoxLayout(section)

        self.config_path_display.setReadOnly(True)
        self.data_dir_display.setReadOnly(True)
        self.credentials_path_display.setReadOnly(True)

        layout.addWidget(QLabel("Config file"))
        layout.addWidget(self.config_path_display)
        layout.addWidget(QLabel("Data directory"))
        layout.addWidget(self.data_dir_display)
        layout.addWidget(QLabel("Credentials file"))
        layout.addWidget(self.credentials_path_display)
        layout.addWidget(self.edit_config_button)
        layout.addWidget(self.reload_config_button)
        return section

    def load_contacts(self) -> None:
        try:
            contact_count = self._load_contacts_into_table()
            self.statusBar().showMessage(f"Loaded {contact_count} contacts.")
        except Exception as exc:
            self._show_error(exc)

    def import_contacts_csv(self) -> None:
        try:
            selected_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Google Contacts CSV",
                str(self.app_paths.data_dir),
                "CSV Files (*.csv)",
            )
            if not selected_path:
                self.statusBar().showMessage("CSV import cancelled.")
                return
            csv_path = Path(selected_path)
            stats = import_google_contacts_csv(
                csv_path=csv_path,
                db_path=self.contacts_db_path,
            )
            contact_count = self._load_contacts_into_table()
            self.statusBar().showMessage(
                f"Imported {stats.written_count} contacts from {csv_path}. "
                f"Showing {contact_count} contacts."
            )
        except Exception as exc:
            self._show_error(exc)

    def sync_google_contacts(self) -> None:
        try:
            resolved_paths = resolve_google_sync_paths(app_paths=self.app_paths)
            ensure_google_credentials_file(resolved_paths.credentials_path)
            stats = sync_google_contacts(
                credentials_path=resolved_paths.credentials_path,
                token_path=resolved_paths.token_path,
                db_path=resolved_paths.db_path,
                source_account="default",
            )
            contact_count = self._load_contacts_into_table()
            self.statusBar().showMessage(
                f"Synced Google contacts: {stats.fetched_count} fetched, "
                f"{stats.written_count} written, {stats.deactivated_count} deactivated. "
                f"Showing {contact_count} contacts."
            )
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

    def edit_contact_columns(self) -> None:
        dialog = ContactsColumnsDialog(
            columns=TablePresenter.contact_columns(),
            visible_column_ids=self.visible_contact_column_ids,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Contact columns edit cancelled.")
            return
        self.visible_contact_column_ids = dialog.selected_column_ids()
        self._save_visible_contact_column_ids()
        contact_count = self._load_contacts_into_table()
        self.statusBar().showMessage(
            f"Updated contact columns. Showing {contact_count} contacts."
        )

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

    def _handle_table_item_double_clicked(self, _: object) -> None:
        if self.table_presenter.current_view_name != "contacts":
            return
        metadata = self.table_presenter.current_row_metadata()
        if not metadata or metadata.get("contact_id") is None:
            return
        try:
            repository = ContactsRepository(self.contacts_db_path)
            repository.initialize()
            contact_details = repository.get_contact_details(contact_id=int(metadata["contact_id"]))
            dialog = ContactDetailsDialog(contact_details=contact_details, parent=self)
            dialog.exec()
        except Exception as exc:
            self._show_error(exc)

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

    def edit_config(self) -> None:
        dialog = ConfigDialog(app_paths=self.app_paths, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Config edit cancelled.")
            return

        app_paths = write_app_paths(
            data_dir=dialog.selected_data_dir(),
            credentials_path=dialog.selected_credentials_path(),
            config_path=self.app_paths.config_path,
        )
        self._apply_app_paths(app_paths)
        self.statusBar().showMessage(f"Saved config to {app_paths.config_path}.")

    def reload_config(self) -> None:
        self._apply_app_paths(get_app_paths())
        self.statusBar().showMessage(f"Reloaded config from {self.app_paths.config_path}.")

    def _apply_app_paths(self, app_paths: AppPaths) -> None:
        self.app_paths = app_paths
        self.contacts_db_path = app_paths.contacts_db
        self.results_db_path = app_paths.race_results_db
        self._invalidate_matching_cache()
        self._refresh_config_summary()

    def _refresh_config_summary(self) -> None:
        self.config_path_display.setText(str(self.app_paths.config_path or ""))
        self.data_dir_display.setText(str(self.app_paths.data_dir))
        if self.app_paths.credentials_path is not None:
            credentials_text = str(self.app_paths.credentials_path)
        else:
            credentials_text = f"(fallback) {default_credentials_path()}"
        self.credentials_path_display.setText(credentials_text)

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

    def _build_menu(self) -> None:
        self.help_menu = self.menuBar().addMenu("Help")
        self.about_action = QAction("About", self)
        self.credits_action = QAction("Credits", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.credits_action.triggered.connect(self.show_credits_dialog)
        self.help_menu.addAction(self.about_action)
        self.help_menu.addAction(self.credits_action)

    def _apply_icons(self) -> None:
        apply_button_icon(
            self.contacts_load_button,
            standard_pixmap=QStyle.StandardPixmap.SP_BrowserReload,
        )
        apply_button_icon(
            self.contacts_sync_button,
            standard_pixmap=QStyle.StandardPixmap.SP_DialogApplyButton,
        )
        apply_button_icon(
            self.contacts_import_button,
            standard_pixmap=QStyle.StandardPixmap.SP_DialogOpenButton,
        )
        apply_button_icon(
            self.contacts_export_button,
            standard_pixmap=QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        apply_button_icon(
            self.contacts_columns_button,
            standard_pixmap=QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        apply_button_icon(
            self.list_datasets_button,
            standard_pixmap=QStyle.StandardPixmap.SP_FileDialogContentsView,
        )
        apply_button_icon(
            self.show_results_button,
            standard_pixmap=QStyle.StandardPixmap.SP_FileDialogListView,
        )
        apply_button_icon(
            self.fetch_acn_button,
            standard_pixmap=QStyle.StandardPixmap.SP_ArrowDown,
        )
        apply_button_icon(
            self.add_alias_button,
            standard_pixmap=QStyle.StandardPixmap.SP_FileDialogNewFolder,
        )
        apply_button_icon(
            self.run_matching_button,
            standard_pixmap=QStyle.StandardPixmap.SP_MediaPlay,
        )
        apply_button_icon(
            self.export_matches_button,
            standard_pixmap=QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        apply_button_icon(
            self.edit_config_button,
            standard_pixmap=QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        apply_button_icon(
            self.reload_config_button,
            standard_pixmap=QStyle.StandardPixmap.SP_BrowserReload,
        )
        apply_action_icon(
            self.about_action,
            owner=self,
            standard_pixmap=QStyle.StandardPixmap.SP_MessageBoxInformation,
        )
        apply_action_icon(
            self.credits_action,
            owner=self,
            standard_pixmap=QStyle.StandardPixmap.SP_DialogHelpButton,
        )

    def _apply_tooltips(self) -> None:
        self.help_menu.setToolTipsVisible(True)
        self.help_menu.setToolTip("Open application help and credits.")
        self.about_action.setToolTip("Show a short description of the desktop application.")
        self.about_action.setStatusTip(self.about_action.toolTip())
        self.credits_action.setToolTip("Show the main technologies and credits behind the app.")
        self.credits_action.setStatusTip(self.credits_action.toolTip())

        self.contacts_query_input.setToolTip(
            "Filter the local contacts table by name, email address, or phone number."
        )
        self.contacts_load_button.setToolTip(
            "Reload contacts from the local SQLite database and show them in the main table."
        )
        self.contacts_sync_button.setToolTip(
            "Sync Google Contacts into the local SQLite database using the configured credentials."
        )
        self.contacts_import_button.setToolTip(
            "Import a Google Contacts CSV export into the local contacts database."
        )
        self.contacts_export_button.setToolTip(
            "Export the current local contacts cache to a JSON file."
        )
        self.contacts_columns_button.setToolTip(
            "Choose which contact columns are visible in the table."
        )

        self.results_url_input.setToolTip(
            "Paste the public ACN Timing URL of a race to fetch and store it locally."
        )
        self.results_dataset_input.setToolTip(
            "Enter a dataset id or alias to inspect stored race results."
        )
        self.results_alias_input.setToolTip(
            "Enter a memorable alias for the currently selected dataset."
        )
        self.list_datasets_button.setToolTip(
            "List all stored race datasets in the main table."
        )
        self.show_results_button.setToolTip(
            "Show the stored results for the dataset id or alias entered above."
        )
        self.fetch_acn_button.setToolTip(
            "Fetch an ACN Timing race from the URL above and save it to the local database."
        )
        self.add_alias_button.setToolTip(
            "Attach the alias above to the currently selected or entered dataset."
        )

        self.matching_dataset_input.setToolTip(
            "Enter the dataset id or alias to run matching on."
        )
        self.matching_status_combo.setToolTip(
            "Filter matches by accepted rows, ambiguous rows, or both."
        )
        self.matching_sort_combo.setToolTip(
            "Choose how matching rows are sorted in the table."
        )
        self.matching_team_input.setToolTip(
            "Filter matching rows by team name."
        )
        self.matching_name_query_input.setToolTip(
            "Filter matching rows by athlete name or matched contact name."
        )
        self.matching_category_input.setToolTip(
            "Filter matching rows by race category."
        )
        self.matching_reviewed_only_checkbox.setToolTip(
            "Only show rows that were explicitly reviewed in the local database."
        )
        self.run_matching_button.setToolTip(
            "Run or refresh matching for the selected dataset using the local contacts database."
        )
        self.export_matches_button.setToolTip(
            "Export the currently visible matching rows to a CSV file."
        )

        self.config_path_display.setToolTip(
            "Read-only path to the current application config file."
        )
        self.data_dir_display.setToolTip(
            "Read-only path to the current local data directory."
        )
        self.credentials_path_display.setToolTip(
            "Read-only path to the configured Google credentials file, if any."
        )
        self.edit_config_button.setToolTip(
            "Edit the configured data directory and optional credentials file."
        )
        self.reload_config_button.setToolTip(
            "Reload the application config from disk."
        )

        self.controls_tabs.setToolTip(
            "Use these tabs to switch between contacts, race results, matching, and config tools."
        )
        self.table.setToolTip(
            "Main results table. Double-click a contact row to open its detailed local record."
        )

    def _load_contacts_into_table(self) -> int:
        repository = ContactsRepository(self.contacts_db_path)
        repository.initialize()
        query = self._clean_text(self.contacts_query_input.text())
        contacts = repository.list_contacts(query=query)
        self.table_presenter.show_contacts(
            contacts,
            visible_column_ids=self.visible_contact_column_ids,
        )
        return len(contacts)

    def _auto_load_contacts_on_startup(self) -> None:
        if not self.contacts_db_path.exists():
            return
        try:
            contact_count = self._load_contacts_into_table()
        except Exception as exc:
            self._show_error(exc)
            return
        if contact_count > 0:
            self.statusBar().showMessage(f"Loaded {contact_count} contacts.")
        else:
            self.table_presenter.show_placeholder("No data loaded yet.")
            self.statusBar().showMessage("GUI ready.")

    def _load_visible_contact_column_ids(self) -> list[str]:
        default_ids = [
            column.key
            for column in TablePresenter.contact_columns()
            if column.default_visible
        ]
        raw_value = self.settings.value(CONTACT_COLUMNS_SETTINGS_KEY)
        if raw_value is None:
            return default_ids
        try:
            if isinstance(raw_value, str):
                stored_ids = json.loads(raw_value)
            elif isinstance(raw_value, list):
                stored_ids = raw_value
            else:
                return default_ids
        except json.JSONDecodeError:
            return default_ids
        if not isinstance(stored_ids, list):
            return default_ids
        stored_set = {str(column_id) for column_id in stored_ids}
        resolved_ids = [
            column.key
            for column in TablePresenter.contact_columns()
            if column.key in stored_set
        ]
        return resolved_ids or default_ids

    def _save_visible_contact_column_ids(self) -> None:
        self.settings.setValue(
            CONTACT_COLUMNS_SETTINGS_KEY,
            json.dumps(self.visible_contact_column_ids),
        )
        self.settings.sync()

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About match-my-contacts",
            (
                "match-my-contacts is a local desktop tool for browsing contacts, "
                "importing race results, and reviewing matches."
            ),
        )

    def show_credits_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Credits",
            (
                "Built with PySide6 on top of the local-first match-my-contacts "
                "storage and matching services."
            ),
        )
