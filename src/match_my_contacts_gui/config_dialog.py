from __future__ import annotations

from pathlib import Path

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


class ConfigDialog(QDialog):
    def __init__(self, *, app_paths: AppPaths, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_paths = app_paths

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
        selected_dir = QFileDialog.getExistingDirectory(self, "Select data directory", self.data_dir_input.text())
        if selected_dir:
            self.data_dir_input.setText(selected_dir)

    def _choose_credentials_file(self) -> None:
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select credentials.json",
            self.credentials_path_input.text(),
            "JSON Files (*.json)",
        )
        if selected_file:
            self.credentials_path_input.setText(selected_file)

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
