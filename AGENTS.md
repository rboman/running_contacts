# Repository Guidelines

## Project Structure & Module Organization
Core Python code lives in `src/running_contacts/`. The CLI entry point is `src/running_contacts/cli.py`, exposed as the `running-contacts` console script via `pyproject.toml`. Organize code by reusable domain modules such as `contacts`, `race_results`, and `matching`; avoid putting business logic directly in CLI commands. Use `tests/` for automated tests and `data/` only for local runtime artifacts like SQLite databases, raw snapshots, exports, and OAuth tokens.

## Build, Test, and Development Commands
Create a virtual environment and install the package in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the CLI locally with `running-contacts hello` to confirm the entry point works. Use `pytest -q` to run tests. At the moment the suite is empty, so contributors adding behavior should add tests alongside the change.
Run the CLI locally with `running-contacts hello` to confirm the entry point works. Use `running-contacts contacts sync --credentials /path/to/credentials.json` for the Google Contacts slice, `running-contacts race-results fetch-acn --url 'https://…'` for ACN Timing ingestion, `running-contacts matching run --dataset-id 1` for local matching, `running-contacts contacts add-alias --contact-id 42 --alias 'Jean Noel'` or `running-contacts matching accept --dataset-id 1 --result-id 1234 --contact-id 42` for manual correction, `running-contacts contacts list` or `running-contacts race-results list-datasets` to inspect local caches, and `pytest -q` to run tests.

## Coding Style & Naming Conventions
Target Python 3.11+ and prefer the standard library where practical. Follow PEP 8: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and short, explicit docstrings where they add value. Keep CLI commands thin: put I/O orchestration in service modules and persistence in repository-style modules. Typing is expected for public functions, parsing code, and data models.

## Testing Guidelines
Use `pytest` for all automated tests. Mirror the package structure under `tests/`; for example, logic added in `src/running_contacts/race_results/storage.py` should usually get coverage in `tests/test_race_results_storage.py`. Prefer focused unit tests over live network tests; mock Google/API clients and test URL parsing, mapping, persistence, normalization, and CLI behavior locally. Add regression tests for bug fixes.

## Commit & Pull Request Guidelines
Recent history uses short, imperative commit subjects such as `Add gitignore and initial project skeleton`. Keep that pattern: one-line summary, imperative mood, and specific scope. Pull requests should explain the functional change, note any new commands or data expectations, and link related issues or notes when relevant. Include CLI examples when behavior visible to users changes.

## Data & Configuration Notes
Treat `data/` as local workspace data. Do not commit private contact exports, credentials, OAuth tokens, generated race datasets, match exports, or manual review artifacts unless they are sanitized and intentionally added as fixtures. SQLite is the local source of truth; JSON and CSV are export/debug formats, not the primary store.
