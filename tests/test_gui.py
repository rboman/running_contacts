from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from match_my_contacts.contacts.models import ContactMethod, ContactRecord
from match_my_contacts.contacts.storage import ContactsRepository
from match_my_contacts.matching.models import MatchReport, MatchResult
from match_my_contacts.race_results.models import RaceDataset, RaceFetchStats, RaceResultRow
from match_my_contacts.race_results.storage import RaceResultsRepository


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox, QStatusBar, QTableWidget

from match_my_contacts.config import get_app_paths
from match_my_contacts_gui.main_window import MainWindow


@pytest.fixture
def qt_app() -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


def test_main_window_smoke(qt_app: QApplication, tmp_path: Path) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=tmp_path / "race_results.sqlite3",
    )

    assert isinstance(window.findChild(QGroupBox, "contacts_section"), QGroupBox)
    assert isinstance(window.findChild(QGroupBox, "race_results_section"), QGroupBox)
    assert isinstance(window.findChild(QGroupBox, "matching_section"), QGroupBox)
    assert isinstance(window.findChild(QGroupBox, "config_section"), QGroupBox)
    assert isinstance(window.findChild(QTableWidget, "central_table"), QTableWidget)
    assert isinstance(window.statusBar(), QStatusBar)
    assert window.table.item(0, 0).text() == "No data loaded yet."

    window.close()


def test_main_window_uses_tabs_for_left_side_controls(qt_app: QApplication, tmp_path: Path) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    assert window.controls_tabs.count() == 4
    assert window.controls_tabs.tabText(0) == "Contacts"
    assert window.controls_tabs.tabText(1) == "Race Results"
    assert window.controls_tabs.tabText(2) == "Matching"
    assert window.controls_tabs.tabText(3) == "Config"

    window.close()


def test_main_window_uses_configured_default_paths(qt_app: QApplication) -> None:
    app_paths = get_app_paths()
    repository = ContactsRepository(app_paths.contacts_db)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                raw_payload={"resourceName": "people/1"},
            )
        ],
        sync_run_id=sync_run_id,
    )
    window = MainWindow(settings=build_gui_settings(app_paths.data_dir / "gui-settings.ini"))

    window.contacts_load_button.click()
    qt_app.processEvents()

    assert window.contacts_db_path == app_paths.contacts_db
    assert window.results_db_path == app_paths.race_results_db
    assert window.data_dir_display.text() == str(app_paths.data_dir)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Alice Example"

    window.close()


def test_edit_config_updates_main_window_paths(qt_app: QApplication, tmp_path: Path, monkeypatch: object) -> None:
    new_data_dir = tmp_path / "dropbox-data"
    new_credentials = tmp_path / "shared-credentials.json"
    window = MainWindow(settings=build_gui_settings(tmp_path / "gui-settings.ini"))

    class FakeDialog:
        def __init__(self, *, app_paths: object, parent: object) -> None:
            pass

        def exec(self) -> int:
            from PySide6.QtWidgets import QDialog

            return QDialog.DialogCode.Accepted

        def selected_data_dir(self) -> Path:
            return new_data_dir

        def selected_credentials_path(self) -> Path:
            return new_credentials

    monkeypatch.setattr("match_my_contacts_gui.main_window.ConfigDialog", FakeDialog)

    window.edit_config_button.click()
    qt_app.processEvents()

    assert window.app_paths.data_dir == new_data_dir.resolve()
    assert window.app_paths.credentials_path == new_credentials.resolve()
    assert window.data_dir_display.text() == str(new_data_dir.resolve())
    assert window.credentials_path_display.text() == str(new_credentials.resolve())
    assert "Saved config" in window.statusBar().currentMessage()

    window.close()


def test_load_contacts_populates_table(qt_app: QApplication, tmp_path: Path) -> None:
    contacts_db = build_contacts_db(tmp_path)
    results_db = tmp_path / "race_results.sqlite3"
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=results_db,
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    window.contacts_load_button.click()
    qt_app.processEvents()

    assert table_headers(window.table) == [
        "id",
        "display_name",
        "email",
        "phone",
        "organization",
        "aliases",
        "notes",
    ]
    assert window.table.rowCount() == 2
    assert window.table.item(0, 1).text() == "Alice Example"
    assert window.table.item(0, 2).text() == "alice@example.com"
    assert window.table.item(0, 3).text() == "+32470123456"
    assert window.table.item(0, 4).text() == "Acme Running"
    assert window.table.item(0, 5).text() == "Alice Ex"
    assert window.table.item(0, 6).text() == "Fast runner"
    assert window.table.item(0, 6).toolTip() == "Fast runner"
    assert window.statusBar().currentMessage() == "Loaded 2 contacts."

    window.close()


def test_contacts_view_applies_compact_initial_column_widths(qt_app: QApplication, tmp_path: Path) -> None:
    contacts_db = build_contacts_db(tmp_path)
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    window.contacts_load_button.click()
    qt_app.processEvents()

    assert window.table.columnWidth(0) == 60
    assert window.table.columnWidth(1) == 180
    assert window.table.columnWidth(2) == 220
    assert window.table.columnWidth(3) == 150
    assert window.table.columnWidth(4) == 180
    assert window.table.columnWidth(5) == 180
    assert window.table.horizontalHeader().stretchSectionCount() == 1

    window.close()


def test_export_contacts_json_through_gui(qt_app: QApplication, tmp_path: Path, monkeypatch: object) -> None:
    contacts_db = build_contacts_db(tmp_path)
    export_path = tmp_path / "exports" / "contacts.json"
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    monkeypatch.setattr(
        "match_my_contacts_gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "JSON Files (*.json)"),
    )

    window.contacts_export_button.click()
    qt_app.processEvents()

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload[0]["display_name"] == "Alice Example"
    assert window.statusBar().currentMessage() == f"Exported contacts to {export_path}."

    window.close()


def test_list_datasets_populates_table(qt_app: QApplication, tmp_path: Path) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=build_race_results_db(tmp_path),
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    window.list_datasets_button.click()
    qt_app.processEvents()

    assert table_headers(window.table) == [
        "id",
        "event_title",
        "event_date",
        "event_location",
        "report",
        "aliases",
        "rows",
    ]
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Demo Race"
    assert window.table.item(0, 5).text() == "demo-race"
    assert window.statusBar().currentMessage() == "Loaded 1 datasets."

    window.close()


def test_fetch_acn_dataset_through_gui(qt_app: QApplication, tmp_path: Path, monkeypatch: object) -> None:
    results_db = tmp_path / "race_results.sqlite3"
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=results_db,
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    def fake_fetch_acn_results(*, url: str, db_path: Path, raw_dir: Path) -> RaceFetchStats:
        assert "acn-timing" in url
        assert db_path == results_db
        assert raw_dir.name == "acn_timing"
        repository = RaceResultsRepository(db_path)
        repository.initialize()
        dataset_id = repository.save_dataset(dataset=make_race_dataset(), results=make_race_results())
        return RaceFetchStats(dataset_id=dataset_id, results_count=1)

    monkeypatch.setattr("match_my_contacts_gui.main_window.fetch_acn_results", fake_fetch_acn_results)
    window.results_url_input.setText("https://www.acn-timing.com/demo")

    window.fetch_acn_button.click()
    qt_app.processEvents()

    assert table_headers(window.table) == [
        "id",
        "event_title",
        "event_date",
        "event_location",
        "report",
        "aliases",
        "rows",
    ]
    assert window.table.rowCount() == 1
    assert window.results_dataset_input.text() == "1"
    assert window.matching_dataset_input.text() == "1"
    assert "Fetched ACN dataset 1 with 1 results. Loaded 1 datasets." == window.statusBar().currentMessage()

    window.close()


def test_show_results_populates_table(qt_app: QApplication, tmp_path: Path) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=build_race_results_db(tmp_path),
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    window.results_dataset_input.setText("demo-race")

    window.show_results_button.click()
    qt_app.processEvents()

    assert table_headers(window.table) == [
        "id",
        "position",
        "athlete_name",
        "finish_time",
        "team",
        "bib",
        "category",
    ]
    assert window.table.rowCount() == 2
    assert window.table.item(0, 2).text() == "Alice Example"
    assert "Showing 2 results for dataset 1." == window.statusBar().currentMessage()

    window.close()


def test_add_dataset_alias_uses_current_dataset(qt_app: QApplication, tmp_path: Path) -> None:
    results_db = build_race_results_db(tmp_path)
    repository = RaceResultsRepository(results_db)
    repository.initialize()
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=results_db,
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    window.list_datasets_button.click()
    qt_app.processEvents()
    window.table.selectRow(0)
    window.results_alias_input.setText("demo-updated")

    window.add_alias_button.click()
    qt_app.processEvents()

    assert repository.resolve_dataset_selector("demo-updated") == 1
    assert window.results_dataset_input.text() == "demo-updated"
    assert window.matching_dataset_input.text() == "demo-updated"
    assert window.statusBar().currentMessage() == "Added alias to dataset 1: demo-updated"

    window.close()


def test_matching_filters_update_table_without_rerunning(qt_app: QApplication, tmp_path: Path, monkeypatch: object) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=build_race_results_db(tmp_path),
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    window.matching_dataset_input.setText("demo-race")
    fake_report = make_match_report()
    call_count = {"count": 0}

    def fake_match_dataset(**_: object) -> MatchReport:
        call_count["count"] += 1
        return fake_report

    monkeypatch.setattr("match_my_contacts_gui.main_window.match_dataset", fake_match_dataset)

    window.run_matching_button.click()
    qt_app.processEvents()

    assert call_count["count"] == 1
    assert table_headers(window.table) == [
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
    ]
    assert window.table.rowCount() == 1
    assert window.table.item(0, 2).text() == "Alice Example"

    window.matching_status_combo.setCurrentText("all")
    qt_app.processEvents()
    assert call_count["count"] == 1
    assert window.table.rowCount() == 2

    window.matching_team_input.setText("Club B")
    qt_app.processEvents()
    assert call_count["count"] == 1
    assert window.table.rowCount() == 1
    assert window.table.item(0, 2).text() == "Bob Example"
    assert window.table.item(0, 1).text() == "ambiguous"

    window.close()


def test_export_matches_csv_through_gui(qt_app: QApplication, tmp_path: Path, monkeypatch: object) -> None:
    contacts_db = build_contacts_db(tmp_path)
    results_db = build_race_results_db(tmp_path)
    export_path = tmp_path / "exports" / "matches.csv"
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=results_db,
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    monkeypatch.setattr(
        "match_my_contacts_gui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "CSV Files (*.csv)"),
    )
    window.matching_dataset_input.setText("demo-race")

    window.run_matching_button.click()
    qt_app.processEvents()
    window.matching_team_input.setText("Club A")
    qt_app.processEvents()
    window.export_matches_button.click()
    qt_app.processEvents()

    content = export_path.read_text(encoding="utf-8")
    assert "Alice Example" in content
    assert "Bob Example" not in content
    assert window.statusBar().currentMessage() == f"Exported 1 matches to {export_path}."

    window.close()


def test_list_datasets_uses_table_presenter(qt_app: QApplication, tmp_path: Path) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=build_race_results_db(tmp_path),
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    calls: list[int] = []
    initial_headers = table_headers(window.table)
    initial_rows = window.table.rowCount()

    def fake_show_datasets(datasets: list[dict[str, object]]) -> None:
        calls.append(len(datasets))

    window.table_presenter.show_datasets = fake_show_datasets  # type: ignore[method-assign]

    window.list_datasets_button.click()
    qt_app.processEvents()

    assert calls == [1]
    assert table_headers(window.table) == initial_headers
    assert window.table.rowCount() == initial_rows

    window.close()


def test_main_window_exposes_help_menu_actions(qt_app: QApplication, tmp_path: Path) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    menu_actions = window.menuBar().actions()
    assert [action.text() for action in menu_actions] == ["Help"]
    help_menu = menu_actions[0].menu()
    assert help_menu is not None
    assert [action.text() for action in help_menu.actions()] == ["About", "Credits"]

    window.close()


def test_main_window_auto_loads_contacts_when_database_exists(qt_app: QApplication, tmp_path: Path) -> None:
    contacts_db = build_contacts_db(tmp_path)
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    qt_app.processEvents()

    assert table_headers(window.table) == [
        "id",
        "display_name",
        "email",
        "phone",
        "organization",
        "aliases",
        "notes",
    ]
    assert window.table.rowCount() == 2
    assert window.statusBar().currentMessage() == "Loaded 2 contacts."

    window.close()


def test_main_window_keeps_placeholder_when_contacts_db_is_missing(
    qt_app: QApplication, tmp_path: Path
) -> None:
    contacts_db = tmp_path / "missing" / "contacts.sqlite3"
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )

    qt_app.processEvents()

    assert contacts_db.exists() is False
    assert window.table.item(0, 0).text() == "No data loaded yet."
    assert window.statusBar().currentMessage() == "GUI ready."

    window.close()


def test_contact_columns_can_be_saved_and_restored(
    qt_app: QApplication, tmp_path: Path, monkeypatch: object
) -> None:
    contacts_db = build_contacts_db(tmp_path)
    settings_path = tmp_path / "gui-settings.ini"
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(settings_path),
    )

    class FakeDialog:
        def __init__(self, *, columns: object, visible_column_ids: object, parent: object) -> None:
            pass

        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

        def selected_column_ids(self) -> list[str]:
            return ["display_name", "email", "organization"]

    monkeypatch.setattr("match_my_contacts_gui.main_window.ContactsColumnsDialog", FakeDialog)

    window.contacts_columns_button.click()
    qt_app.processEvents()

    assert table_headers(window.table) == ["display_name", "email", "organization"]
    window.close()

    restored_window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(settings_path),
    )

    assert table_headers(restored_window.table) == ["display_name", "email", "organization"]
    restored_window.close()


def test_double_click_contact_opens_details_dialog(
    qt_app: QApplication, tmp_path: Path, monkeypatch: object
) -> None:
    contacts_db = build_contacts_db(tmp_path)
    window = MainWindow(
        contacts_db_path=contacts_db,
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    captured: dict[str, object] = {}

    class FakeDialog:
        def __init__(self, *, contact_details: dict[str, object], parent: object) -> None:
            captured["contact_details"] = contact_details

        def exec(self) -> int:
            captured["opened"] = True
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("match_my_contacts_gui.main_window.ContactDetailsDialog", FakeDialog)

    window.table.selectRow(0)
    window.table.itemDoubleClicked.emit(window.table.item(0, 0))
    qt_app.processEvents()

    assert captured["opened"] is True
    contact_details = captured["contact_details"]
    assert isinstance(contact_details, dict)
    assert contact_details["display_name"] == "Alice Example"
    assert contact_details["raw_json_text"]

    window.close()


def test_double_click_non_contacts_does_not_open_details_dialog(
    qt_app: QApplication, tmp_path: Path, monkeypatch: object
) -> None:
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=build_race_results_db(tmp_path),
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    opened = {"count": 0}

    class FakeDialog:
        def __init__(self, *, contact_details: dict[str, object], parent: object) -> None:
            pass

        def exec(self) -> int:
            opened["count"] += 1
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("match_my_contacts_gui.main_window.ContactDetailsDialog", FakeDialog)

    window.list_datasets_button.click()
    qt_app.processEvents()
    window.table.selectRow(0)
    window.table.itemDoubleClicked.emit(window.table.item(0, 0))
    qt_app.processEvents()

    assert opened["count"] == 0

    window.close()


def test_import_contacts_csv_through_gui(
    qt_app: QApplication, tmp_path: Path, monkeypatch: object
) -> None:
    csv_path = tmp_path / "google-contacts.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Name,Given Name,Family Name,Nickname,Notes,Organization 1 - Name,E-mail 1 - Type,E-mail 1 - Value,Phone 1 - Type,Phone 1 - Value",
                "Alice Example,Alice,Example,Ali,Fast runner,Acme Running,Home,alice@example.com,Mobile,+32 470 12 34 56",
            ]
        ),
        encoding="utf-8",
    )
    window = MainWindow(
        contacts_db_path=tmp_path / "contacts.sqlite3",
        results_db_path=tmp_path / "race_results.sqlite3",
        settings=build_gui_settings(tmp_path / "gui-settings.ini"),
    )
    monkeypatch.setattr(
        "match_my_contacts_gui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(csv_path), "CSV Files (*.csv)"),
    )

    window.contacts_import_button.click()
    qt_app.processEvents()

    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Alice Example"
    assert "Imported 1 contacts from" in window.statusBar().currentMessage()
    assert "Showing 1 contacts." in window.statusBar().currentMessage()

    window.close()


def build_contacts_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "contacts.sqlite3"
    repository = ContactsRepository(db_path)
    repository.initialize()
    sync_run_id = repository.begin_sync_run(source="google_people", source_account="default")
    repository.replace_contacts(
        source="google_people",
        source_account="default",
        sync_run_id=sync_run_id,
        contacts=[
            ContactRecord(
                source_contact_id="people/1",
                display_name="Alice Example",
                given_name="Alice",
                family_name="Example",
                organization="Acme Running",
                notes="Fast runner",
                methods=[
                    ContactMethod(kind="email", value="alice@example.com"),
                    ContactMethod(kind="phone", value="+32470123456"),
                ],
                raw_payload={"resourceName": "people/1"},
            ),
            ContactRecord(
                source_contact_id="people/2",
                display_name="Bob Example",
                given_name="Bob",
                family_name="Example",
                organization="Beta Club",
                notes="Prefers email",
                methods=[
                    ContactMethod(kind="email", value="bob@example.com"),
                    ContactMethod(kind="phone", value="+32470999888"),
                ],
                raw_payload={"resourceName": "people/2"},
            ),
        ],
    )
    contact_id = int(repository.list_contacts(query="Alice")[0]["id"])
    repository.add_alias(contact_id=contact_id, alias_text="Alice Ex")
    return db_path


def build_race_results_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "race_results.sqlite3"
    repository = RaceResultsRepository(db_path)
    repository.initialize()
    dataset_id = repository.save_dataset(
        dataset=make_race_dataset(),
        results=make_race_results(),
    )
    repository.add_dataset_alias(dataset_id=dataset_id, alias_text="demo-race")
    return db_path


def make_race_dataset() -> RaceDataset:
    return RaceDataset(
        provider="acn_timing",
        source_url="https://example.test",
        external_event_id="1",
        context_db="demo",
        report_key="LIVE1",
        report_path="path",
        event_title="Demo Race",
        event_date="12/04/2026",
        event_location="Liege",
        event_country="BEL",
        total_results=2,
        metadata={},
    )


def make_race_results() -> list[RaceResultRow]:
    return [
        RaceResultRow(
            group_name=None,
            group_rank=1,
            position_text="1",
            bib="101",
            athlete_name="Alice Example",
            team="Club A",
            finish_time="0:40:00",
            category="SEF",
            raw_row=["Alice Example"],
        ),
        RaceResultRow(
            group_name=None,
            group_rank=2,
            position_text="2",
            bib="102",
            athlete_name="Bob Example",
            team="Club B",
            finish_time="0:42:00",
            category="SEH",
            raw_row=["Bob Example"],
        ),
    ]


def make_match_report() -> MatchReport:
    return MatchReport(
        dataset={"id": 1, "event_title": "Demo Race"},
        accepted_matches=[
            MatchResult(
                status="accepted",
                match_method="exact",
                score=100.0,
                matched_alias="Alice Example",
                confidence_gap=100.0,
                result_id=1,
                dataset_id=1,
                athlete_name="Alice Example",
                position_text="1",
                bib="101",
                finish_time="0:40:00",
                team="Club A",
                category="SEF",
                contact_id=1,
                contact_name="Alice Example",
            )
        ],
        ambiguous_matches=[
            MatchResult(
                status="ambiguous",
                match_method="fuzzy",
                score=96.0,
                matched_alias="Bob Example",
                confidence_gap=1.0,
                result_id=2,
                dataset_id=1,
                athlete_name="Bob Example",
                position_text="2",
                bib="102",
                finish_time="0:42:00",
                team="Club B",
                category="SEH",
                contact_id=2,
                contact_name="Bob Example",
            )
        ],
        unmatched_count=0,
        contacts_count=2,
        results_count=2,
    )


def table_headers(table: QTableWidget) -> list[str]:
    return [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())]


def build_gui_settings(path: Path) -> QSettings:
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    return settings
