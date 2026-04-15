from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from match_my_contacts.config import AppPaths


CONFIG_DATA_DIR_DIALOG_SETTINGS_KEY = "file_dialogs/config_data_dir"
CONFIG_CREDENTIALS_DIALOG_SETTINGS_KEY = "file_dialogs/config_credentials_file"


class ConfigDialog(QDialog):
    def __init__(
        self,
        *,
        app_paths: AppPaths,
        parent: QWidget | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_paths = app_paths
        self._settings = settings or QSettings("match-my-contacts", "match-my-contacts-gui")

        self.setWindowTitle("Configuration")
        self.resize(720, 220)

        self.config_path_label = QLabel(str(app_paths.config_path or ""))
        self.data_dir_input = QLineEdit(str(app_paths.data_dir))
        self.credentials_path_input = QLineEdit(
            str(app_paths.credentials_path) if app_paths.credentials_path is not None else ""
        )
        self.config_path_label.setToolTip("Read-only path to the current config file.")
        self.data_dir_input.setToolTip("Choose where local SQLite databases, exports, and tokens are stored.")
        self.credentials_path_input.setToolTip(
            "Optional path to the Google OAuth credentials JSON file used by CLI sync commands."
        )

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Config file", self.config_path_label)
        form_layout.addRow("Data directory", self._row_with_button(self.data_dir_input, self._choose_data_dir))
        form_layout.addRow(
            "Credentials file",
            self._row_with_button(self.credentials_path_input, self._choose_credentials_file),
        )
        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button is not None:
            ok_button.setToolTip("Save these config values to disk.")
        if cancel_button is not None:
            cancel_button.setToolTip("Close this dialog without saving changes.")
        layout.addWidget(buttons)

    def selected_data_dir(self) -> Path:
        return Path(self.data_dir_input.text().strip()).expanduser()

    def selected_credentials_path(self) -> Path | None:
        raw_value = self.credentials_path_input.text().strip()
        if not raw_value:
            return None
        return Path(raw_value).expanduser()

    def _choose_data_dir(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select data directory",
            self._dialog_start_directory(
                CONFIG_DATA_DIR_DIALOG_SETTINGS_KEY,
                fallback_path=Path(self.data_dir_input.text() or self._app_paths.data_dir),
            ),
        )
        if selected_dir:
            self.data_dir_input.setText(selected_dir)
            self._remember_dialog_path(CONFIG_DATA_DIR_DIALOG_SETTINGS_KEY, Path(selected_dir))

    def _choose_credentials_file(self) -> None:
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select credentials.json",
            self._dialog_start_directory(
                CONFIG_CREDENTIALS_DIALOG_SETTINGS_KEY,
                fallback_path=Path(
                    self.credentials_path_input.text()
                    or self._app_paths.credentials_path
                    or self._app_paths.data_dir
                ),
            ),
            "JSON Files (*.json)",
        )
        if selected_file:
            self.credentials_path_input.setText(selected_file)
            self._remember_dialog_path(
                CONFIG_CREDENTIALS_DIALOG_SETTINGS_KEY,
                Path(selected_file),
            )

    def _row_with_button(self, line_edit: QLineEdit, callback: object) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse")
        button.clicked.connect(callback)
        button.setToolTip("Open a file or folder chooser for this setting.")
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return container

    def _dialog_start_directory(self, settings_key: str, *, fallback_path: Path) -> str:
        stored_value = self._settings.value(settings_key)
        if isinstance(stored_value, str) and stored_value.strip():
            return stored_value
        resolved = fallback_path.expanduser()
        if resolved.suffix:
            resolved = resolved.parent
        return str(resolved)

    def _remember_dialog_path(self, settings_key: str, path: Path) -> None:
        resolved = path.expanduser()
        directory = resolved.parent if resolved.suffix else resolved
        self._settings.setValue(settings_key, str(directory))
        self._settings.sync()
