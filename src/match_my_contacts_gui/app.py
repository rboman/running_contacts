from __future__ import annotations

import ctypes.util
import os
import sys


def _detect_qt_startup_issue() -> str | None:
    if sys.platform != "linux":
        return None

    if os.environ.get("QT_QPA_PLATFORM"):
        return None

    session_type = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    has_x11_display = bool(os.environ.get("DISPLAY"))
    has_wayland_display = bool(os.environ.get("WAYLAND_DISPLAY"))
    uses_x11 = session_type == "x11" or (has_x11_display and not has_wayland_display)

    if uses_x11 and ctypes.util.find_library("xcb-cursor") is None:
        return (
            "Qt could not start on Linux/X11 because the system library "
            "`libxcb-cursor0` is missing.\n"
            "Install it with your package manager, for example:\n"
            "  sudo apt install libxcb-cursor0"
        )

    return None


def main() -> int:
    startup_issue = _detect_qt_startup_issue()
    if startup_issue is not None:
        raise SystemExit(startup_issue)

    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is not installed. Run `pip install -e .[gui]` to enable the desktop GUI."
        ) from exc

    from .main_window import MainWindow

    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    application.setWindowIcon(window.windowIcon())
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
