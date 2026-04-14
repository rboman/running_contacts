from __future__ import annotations

from pathlib import Path

from running_contacts.config import (
    default_data_dir,
    ensure_config_exists,
    get_app_paths,
    get_config_path,
    write_app_paths,
)


def test_config_is_auto_created_and_points_to_current_data_dir() -> None:
    config_path = get_config_path()

    assert not config_path.exists()

    ensure_config_exists()

    assert config_path.exists()
    assert default_data_dir() == Path.cwd() / "data"
    app_paths = get_app_paths()
    assert app_paths.data_dir == (Path.cwd() / "data").resolve()
    assert app_paths.contacts_db == app_paths.data_dir / "contacts.sqlite3"
    assert app_paths.race_results_db == app_paths.data_dir / "race_results.sqlite3"
    assert app_paths.google_token == app_paths.data_dir / "google" / "token.json"
    assert app_paths.raw_acn_dir == app_paths.data_dir / "raw" / "acn_timing"
    assert app_paths.contacts_export_json == app_paths.data_dir / "exports" / "contacts.json"
    assert app_paths.matches_export_csv == app_paths.data_dir / "exports" / "matches.csv"


def test_config_can_point_to_custom_shared_data_dir() -> None:
    shared_dir = Path.cwd() / "dropbox" / "running_contacts_data"
    app_paths = write_app_paths(data_dir=shared_dir)

    assert app_paths.data_dir == shared_dir.resolve()
    assert app_paths.config_path == get_config_path()


def test_config_can_store_credentials_path() -> None:
    shared_dir = Path.cwd() / "dropbox" / "running_contacts_data"
    credentials_path = Path.cwd() / "secrets" / "credentials.json"

    app_paths = write_app_paths(data_dir=shared_dir, credentials_path=credentials_path)

    assert app_paths.data_dir == shared_dir.resolve()
    assert app_paths.credentials_path == credentials_path.resolve()
