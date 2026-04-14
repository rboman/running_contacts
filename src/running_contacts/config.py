from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True, frozen=True)
class AppPaths:
    data_dir: Path
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
    ensure_config_exists(config_path=config_path)
    return AppPaths(
        data_dir=load_data_dir(config_path=config_path),
        config_path=config_path,
    )


def build_app_paths(*, data_dir: Path, config_path: Path | None = None) -> AppPaths:
    return AppPaths(data_dir=data_dir.resolve(), config_path=config_path)


def get_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        base_dir = Path(xdg_config_home).expanduser()
    else:
        base_dir = Path.home() / ".config"
    return base_dir / "running_contacts" / "config.toml"


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


def load_data_dir(*, config_path: Path | None = None) -> Path:
    resolved_config_path = ensure_config_exists(config_path=config_path)
    payload = tomllib.loads(resolved_config_path.read_text(encoding="utf-8"))
    raw_data_dir = payload.get("data_dir")
    if not isinstance(raw_data_dir, str) or not raw_data_dir.strip():
        raise RuntimeError(f"Invalid config file: missing or invalid data_dir in {resolved_config_path}")

    data_dir = Path(raw_data_dir).expanduser()
    if not data_dir.is_absolute():
        data_dir = (resolved_config_path.parent / data_dir).resolve()
    return data_dir.resolve()


def default_data_dir() -> Path:
    return (Path.cwd() / "data").resolve()
