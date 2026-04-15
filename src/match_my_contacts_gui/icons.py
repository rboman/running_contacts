from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QPushButton, QStyle, QWidget


def apply_window_icon(window: QWidget) -> None:
    window.setWindowIcon(standard_icon(window, QStyle.StandardPixmap.SP_FileDialogContentsView))


def apply_button_icon(
    button: QPushButton,
    *,
    standard_pixmap: QStyle.StandardPixmap,
) -> None:
    button.setIcon(standard_icon(button, standard_pixmap))


def apply_action_icon(
    action: QAction,
    *,
    owner: QWidget,
    standard_pixmap: QStyle.StandardPixmap,
) -> None:
    action.setIcon(standard_icon(owner, standard_pixmap))


def standard_icon(widget: QWidget, standard_pixmap: QStyle.StandardPixmap):
    return widget.style().standardIcon(standard_pixmap)
