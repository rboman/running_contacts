from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True, frozen=True)
class AppPaths:
    data_dir: Path
    credentials_path: Path | None = None
    config_path: Path | None = None

    @property
    def contacts_db(self) -> Path:
        return self.data_dir / "contacts.sqlite3"

    @property
    def race_results_db(self) -> Path:
        return self.data_dir / "race_results.sqlite3"

    @property
    def google_token(self) -> Path:
        return self.data_dir / "google" / "token.json"

    @property
    def raw_acn_dir(self) -> Path:
        return self.data_dir / "raw" / "acn_timing"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def contacts_export_json(self) -> Path:
        return self.exports_dir / "contacts.json"

    @property
    def race_results_export_json(self) -> Path:
        return self.exports_dir / "race_results.json"

    @property
    def matches_export_csv(self) -> Path:
        return self.exports_dir / "matches.csv"


def get_app_paths() -> AppPaths:
    config_path = get_config_path()
    return load_app_paths(config_path=config_path)


def build_app_paths(*, data_dir: Path, config_path: Path | None = None) -> AppPaths:
    return AppPaths(data_dir=data_dir.resolve(), config_path=config_path)


def get_config_path() -> Path:
    config_home_override = os.environ.get("RUNNING_CONTACTS_CONFIG_HOME")
    if config_home_override:
        base_dir = Path(config_home_override).expanduser()
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            base_dir = Path(appdata).expanduser()
        else:
            base_dir = Path.home() / "AppData" / "Roaming"
    else:
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            base_dir = Path(xdg_config_home).expanduser()
        else:
            base_dir = Path.home() / ".config"
    return base_dir / "running_contacts" / "config.toml"


def get_project_root() -> Path:
    project_root_override = os.environ.get("RUNNING_CONTACTS_PROJECT_ROOT")
    if project_root_override:
        return Path(project_root_override).expanduser().resolve()

    cwd_root = _find_project_root(Path.cwd())
    if cwd_root is not None:
        return cwd_root

    module_root = _find_project_root(Path(__file__).resolve())
    if module_root is not None:
        return module_root

    return Path.cwd().resolve()


def default_credentials_path() -> Path:
    return (get_project_root() / "credentials.json").resolve()


def _find_project_root(start_path: Path) -> Path | None:
    candidate = start_path if start_path.is_dir() else start_path.parent
    for path in (candidate, *candidate.parents):
        if (path / "pyproject.toml").exists():
            return path.resolve()
    return None


def ensure_config_exists(*, config_path: Path | None = None) -> Path:
    resolved_config_path = config_path or get_config_path()
    if resolved_config_path.exists():
        return resolved_config_path

    resolved_config_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_config_path.write_text(
        f"data_dir = {json.dumps(str(default_data_dir()))}\n",
        encoding="utf-8",
    )
    return resolved_config_path


def load_app_paths(*, config_path: Path | None = None) -> AppPaths:
    resolved_config_path = ensure_config_exists(config_path=config_path)
    payload = load_config_payload(config_path=resolved_config_path)
    return AppPaths(
        data_dir=_resolve_configured_path(payload.get("data_dir"), config_path=resolved_config_path),
        credentials_path=_resolve_optional_path(
            payload.get("credentials_path"),
            config_path=resolved_config_path,
        ),
        config_path=resolved_config_path,
    )


def load_config_payload(*, config_path: Path | None = None) -> dict[str, object]:
    resolved_config_path = ensure_config_exists(config_path=config_path)
    payload = tomllib.loads(resolved_config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid config file: expected a TOML table in {resolved_config_path}")
    return payload


def load_data_dir(*, config_path: Path | None = None) -> Path:
    return load_app_paths(config_path=config_path).data_dir


def write_app_paths(
    *,
    data_dir: Path,
    credentials_path: Path | None = None,
    config_path: Path | None = None,
) -> AppPaths:
    resolved_config_path = config_path or get_config_path()
    resolved_config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"data_dir = {json.dumps(str(data_dir.resolve()))}\n"]
    if credentials_path is not None:
        lines.append(f"credentials_path = {json.dumps(str(credentials_path.resolve()))}\n")

    resolved_config_path.write_text("".join(lines), encoding="utf-8")
    return load_app_paths(config_path=resolved_config_path)


def default_data_dir() -> Path:
    return (get_project_root() / "data").resolve()


def _resolve_configured_path(raw_value: object, *, config_path: Path) -> Path:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise RuntimeError(f"Invalid config file: missing or invalid data_dir in {config_path}")
    return _resolve_path_string(raw_value, config_path=config_path)


def _resolve_optional_path(raw_value: object, *, config_path: Path) -> Path | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise RuntimeError(f"Invalid config file: invalid path value in {config_path}")
    return _resolve_path_string(raw_value, config_path=config_path)


def _resolve_path_string(raw_value: str, *, config_path: Path) -> Path:
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path.resolve()
