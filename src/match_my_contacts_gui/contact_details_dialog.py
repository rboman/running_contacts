from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ContactDetailsDialog(QDialog):
    def __init__(
        self,
        *,
        contact_details: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.contact_details = contact_details

        display_name = str(contact_details.get("display_name", "") or "Contact")
        self.setWindowTitle(f"Contact details: {display_name}")
        self.resize(860, 680)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.setToolTip("Inspect the stored contact from different angles.")
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_methods_tab(), "Methods")
        self.tabs.addTab(self._build_aliases_tab(), "Aliases")
        if self.contact_details.get("raw_json_text"):
            self.tabs.addTab(self._build_raw_json_tab(), "Raw JSON")
        self.tabs.setTabToolTip(0, "General identity, source, and timestamp information.")
        self.tabs.setTabToolTip(1, "Stored email addresses and phone numbers for this contact.")
        self.tabs.setTabToolTip(2, "Manual aliases stored for this contact.")
        if self.contact_details.get("raw_json_text"):
            self.tabs.setTabToolTip(3, "Original raw payload stored in the local database.")
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setToolTip("Close this details dialog.")
        layout.addWidget(buttons)

    def _build_overview_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.addRow("Display name", self._value_label(self.contact_details.get("display_name")))
        form.addRow("Given name", self._value_label(self.contact_details.get("given_name")))
        form.addRow("Family name", self._value_label(self.contact_details.get("family_name")))
        form.addRow("Nickname", self._value_label(self.contact_details.get("nickname")))
        form.addRow("Organization", self._value_label(self.contact_details.get("organization")))
        form.addRow("Source", self._value_label(self.contact_details.get("source_display")))
        form.addRow("Source key", self._value_label(self.contact_details.get("source")))
        form.addRow("Source family", self._value_label(self.contact_details.get("source_family")))
        form.addRow("Source behavior", self._value_label(self.contact_details.get("source_behavior")))
        form.addRow(
            "Source syncable",
            self._value_label("yes" if self.contact_details.get("source_syncable") else "no"),
        )
        form.addRow("Source account", self._value_label(self.contact_details.get("source_account")))
        form.addRow("Source contact id", self._value_label(self.contact_details.get("source_contact_id")))
        form.addRow(
            "Status",
            self._value_label("active" if self.contact_details.get("active") else "inactive"),
        )
        form.addRow("Aliases", self._value_label(", ".join(self.contact_details.get("aliases", []))))
        form.addRow("Last seen sync id", self._value_label(self.contact_details.get("last_seen_sync_id")))
        form.addRow("Created at", self._value_label(self.contact_details.get("created_at")))
        form.addRow("Updated at", self._value_label(self.contact_details.get("updated_at")))
        layout.addLayout(form)

        notes = QPlainTextEdit(self)
        notes.setReadOnly(True)
        notes.setPlainText(str(self.contact_details.get("notes", "") or ""))
        notes.setPlaceholderText("No notes.")
        notes.setToolTip("Read-only notes stored for this contact.")
        layout.addWidget(QLabel("Notes"))
        layout.addWidget(notes)
        return page

    def _build_methods_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        methods = self.contact_details.get("methods", [])
        table = QTableWidget(len(methods), 6, self)
        table.setHorizontalHeaderLabels(
            ["kind", "label", "value", "normalized_value", "is_primary", "created_at"]
        )
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setToolTip("Read-only list of stored contact methods.")
        for row_index, method in enumerate(methods):
            values = (
                str(method.get("kind", "") or ""),
                str(method.get("label", "") or ""),
                str(method.get("value", "") or ""),
                str(method.get("normalized_value", "") or ""),
                "yes" if method.get("is_primary") else "no",
                str(method.get("created_at", "") or ""),
            )
            for column_index, value in enumerate(values):
                table.setItem(row_index, column_index, QTableWidgetItem(value))
        layout.addWidget(table)
        return page

    def _build_aliases_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        aliases = self.contact_details.get("alias_records", [])
        table = QTableWidget(len(aliases), 3, self)
        table.setHorizontalHeaderLabels(["alias_text", "normalized_alias", "created_at"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setToolTip("Read-only list of aliases stored for this contact.")
        for row_index, alias in enumerate(aliases):
            values = (
                str(alias.get("alias_text", "") or ""),
                str(alias.get("normalized_alias", "") or ""),
                str(alias.get("created_at", "") or ""),
            )
            for column_index, value in enumerate(values):
                table.setItem(row_index, column_index, QTableWidgetItem(value))
        layout.addWidget(table)
        return page

    def _build_raw_json_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        raw_json = self.contact_details.get("raw_json")
        if isinstance(raw_json, str):
            raw_text = raw_json
        else:
            raw_text = json.dumps(raw_json, ensure_ascii=False, indent=2)
        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlainText(raw_text)
        editor.setToolTip("Original raw JSON payload stored for this contact.")
        layout.addWidget(editor)
        return page

    @staticmethod
    def _value_label(value: object) -> QLabel:
        text = str(value or "")
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(label.textInteractionFlags())
        label.setToolTip(text if text else "No value stored.")
        return label
