from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def isolate_runtime_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("MATCH_MY_CONTACTS_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("MATCH_MY_CONTACTS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def google_contacts_csv_path(tmp_path: Path) -> Path:
    source = FIXTURES / "google_contacts_export_synthetic.csv"
    destination = tmp_path / "google-contacts.csv"
    shutil.copyfile(source, destination)
    return destination
