# Handoff Notes

Read this file first when resuming work on `match-my-contacts` in a later Codex session.

## Current State

- `contacts` now supports multiple local contact sources in the same `contacts.sqlite3` under the configured `data_dir`.
- the currently implemented providers are:
  - `google_people` for Google People API syncs
  - `google_contacts_csv` for Google Contacts CSV snapshot imports
- contacts keep their precise `source`, `source_account`, and `source_contact_id`
- resync and reimport boundaries are isolated per source/account slot
- contacts now expose derived source metadata such as label, behavior, syncability, and display text
- `race_results` is implemented for ACN Timing / Chronorace and stores local datasets in `race_results.sqlite3` under the configured `data_dir`.
- `matching` is implemented with:
  - exact and fuzzy matching,
  - contact aliases,
  - race dataset aliases,
  - manual review commands (`accept`, `reject`, `clear-review`, `list-reviews`),
  - sorted and filtered listing (`matching list`).
- a first desktop GUI is now implemented on top of the existing local-first workflow.
- the default data location is now resolved through a machine-local config file that points to a `data_dir`
- packaging now targets Python `3.10+`; on Python 3.10 the config loader uses `tomli` as a fallback for `tomllib`
- GitHub Actions now runs `pytest -q` on `ubuntu-latest` for Python `3.10` and `3.12`

## GUI Status

Current GUI capabilities:

- load contacts from the local database
- sync Google contacts into the local database
- import Google Contacts CSV exports into the local database
- show a modal success/error dialog after Google sync
- empty the contacts database after a confirmation dialog
- run SQLite `VACUUM` on the contacts database from the GUI
- export contacts to JSON
- choose visible contact columns, including source visibility
- open a read-only contact details dialog with source metadata and raw JSON
- fetch ACN datasets
- list datasets and show stored race results
- add dataset aliases
- run matching with local filters
- export filtered matches to CSV

Still CLI-only for now:

- manual review actions on matches
- advanced source inspection via `contacts list-sources`

## Config / Shared Data

Local config file:

```bash
~/.config/match_my_contacts/config.toml
```

On Windows, use:

```powershell
$env:APPDATA\match_my_contacts\config.toml
```

Supported key:

```toml
data_dir = "/absolute/path/to/match_my_contacts_data"
credentials_path = "/absolute/path/to/credentials.json"
```

All default paths now derive from that directory:

- `contacts.sqlite3`
- `race_results.sqlite3`
- `google/token.json`
- `raw/acn_timing/`
- `exports/`

Recommended shared usage:

1. point `data_dir` to a Dropbox-backed folder on each machine
2. use only one machine at a time on the shared SQLite files
3. wait for Dropbox sync to finish before switching machines

Useful config inspection command:

```bash
match-my-contacts config show
```

## Important Local Selectors

- Main imported race dataset:
  - `dataset_id = 1`
  - alias: `liege-15k-2026`

## Known Current Result

At the time of this handoff, running:

```bash
match-my-contacts matching run --dataset liege-15k-2026
```

returns approximately:

- `47 accepted matches`
- `0 ambiguous`

This can evolve if contacts are resynced or aliases/reviews are changed.

## Manual Cleanup Already Applied

- Added contact alias:
  - contact `972` (`Pierre-Paul Jeunechamps`) -> alias `Pierre Jeunechamps`

Reason:
- this resolved the previous ambiguous race result `JEUNECHAMPS Pierre`.

## Useful Commands

Sync contacts:

```bash
match-my-contacts contacts sync
match-my-contacts contacts sync-google
match-my-contacts contacts import-google-csv --csv-path /path/to/google-contacts.csv
match-my-contacts contacts empty-db
match-my-contacts contacts vacuum-db
match-my-contacts contacts list-sources
```

Inspect contacts and aliases:

```bash
match-my-contacts contacts list --query noel
match-my-contacts contacts list --source google_people
match-my-contacts contacts list --source google_contacts_csv
match-my-contacts contacts list-aliases
```

Inspect races:

```bash
match-my-contacts race-results list-datasets
match-my-contacts race-results list-aliases
match-my-contacts race-results list-results --dataset liege-15k-2026 --query ucci
```

Inspect matches:

```bash
match-my-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 30
match-my-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE --sort time
match-my-contacts matching list --dataset liege-15k-2026 --status all --sort athlete
```

Manual corrections:

```bash
match-my-contacts contacts add-alias --contact-id 691 --alias "Jean Noel"
match-my-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 691
match-my-contacts matching reject --dataset liege-15k-2026 --result-id 5678 --note "homonyme"
match-my-contacts matching list-reviews --dataset liege-15k-2026
```

## How To Resume Codex

Resume the most recent interactive Codex session:

```bash
codex resume --last
```

Open the session picker:

```bash
codex resume
```

If you do not resume the exact same interactive session, start the new session in this repo and point it to:

```bash
README.md
USAGE.md
HANDOFF.md
```

## Recommended Next Work

Most likely next step:

- extend the GUI with a lightweight review workflow for accepted / ambiguous / reviewed results

Why this is the next step:

1. the current matching is considered satisfactory for now
2. the GUI already covers the main local read/import/export flows
3. manual review is now the most obvious remaining daily action still stuck in the CLI

Current GUI scope:

1. `Contacts` section
2. `Race Results` section
3. `Matching` section
4. central table
5. status bar

Run the GUI locally with:

```bash
pip install -e .[gui]
sudo apt install libxcb-cursor0  # if needed on Linux/X11
match-my-contacts-gui
```

Recent GUI additions to keep in mind:

- local contacts auto-load on startup when `contacts.sqlite3` already exists
- `Contacts` can now sync Google and import Google Contacts CSV exports directly from the GUI
- `Sync Google` now shows a modal summary dialog on success and a modal error dialog on failure
- `Contacts` now exposes `Empty DB...` with an explicit destructive-action confirmation
- `Contacts` now exposes `VACUUM DB` to compact `contacts.sqlite3` on demand
- contacts table column visibility is stored in Qt settings, not in `config.toml`
- the optional source column exposes the origin of each contact in the table
- double-clicking a contact row opens a read-only details dialog with DB metadata, source metadata, and raw JSON
- the GUI now includes a `Help` menu with `About` and `Credits`

Current CSV assumption:

- only the real Google Contacts export format is supported in the GUI and CLI importer
- there is still no generic CSV mapping wizard
