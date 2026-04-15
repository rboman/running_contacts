from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from .table_presenter import ContactColumnDefinition


class ContactsColumnsDialog(QDialog):
    def __init__(
        self,
        *,
        columns: tuple[ContactColumnDefinition, ...],
        visible_column_ids: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = columns
        self._checkboxes: dict[str, QCheckBox] = {}

        self.setWindowTitle("Visible contact columns")
        self.resize(360, 320)

        layout = QVBoxLayout(self)
        intro_label = QLabel("Choose which columns to show in the contacts table.")
        intro_label.setToolTip("These preferences are stored locally for future GUI launches.")
        layout.addWidget(intro_label)

        selected = set(visible_column_ids)
        for column in columns:
            checkbox = QCheckBox(column.header.replace("_", " ").title())
            checkbox.setChecked(column.key in selected)
            checkbox.setToolTip(f"Show or hide the '{column.header}' column in the contacts table.")
            self._checkboxes[column.key] = checkbox
            layout.addWidget(checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button is not None:
            ok_button.setToolTip("Save the current visible-column selection.")
        if cancel_button is not None:
            cancel_button.setToolTip("Close this dialog without changing the visible columns.")
        layout.addWidget(buttons)

    def selected_column_ids(self) -> list[str]:
        return [
            column.key
            for column in self._columns
            if self._checkboxes[column.key].isChecked()
        ]

    def accept(self) -> None:
        if not self.selected_column_ids():
            QMessageBox.warning(self, "No columns selected", "Select at least one column.")
            return
        super().accept()
