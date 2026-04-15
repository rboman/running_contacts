# Handoff Notes

Read this file first when resuming work on `running_contacts` in a later Codex session.

## Current State

- `contacts` is implemented and syncs one Google account into `contacts.sqlite3` under the configured `data_dir`.
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
- export contacts to JSON
- fetch ACN datasets
- list datasets and show stored race results
- add dataset aliases
- run matching with local filters
- export filtered matches to CSV

Still CLI-only for now:

- Google Contacts sync
- manual review actions on matches

## Config / Shared Data

Local config file:

```bash
~/.config/running_contacts/config.toml
```

On Windows, use:

```powershell
$env:APPDATA\running_contacts\config.toml
```

Supported key:

```toml
data_dir = "/absolute/path/to/running_contacts_data"
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
running-contacts config show
```

## Important Local Selectors

- Main imported race dataset:
  - `dataset_id = 1`
  - alias: `liege-15k-2026`

## Known Current Result

At the time of this handoff, running:

```bash
running-contacts matching run --dataset liege-15k-2026
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
running-contacts contacts sync
```

Inspect contacts and aliases:

```bash
running-contacts contacts list --query noel
running-contacts contacts list-aliases
```

Inspect races:

```bash
running-contacts race-results list-datasets
running-contacts race-results list-aliases
running-contacts race-results list-results --dataset liege-15k-2026 --query ucci
```

Inspect matches:

```bash
running-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 30
running-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE --sort time
running-contacts matching list --dataset liege-15k-2026 --status all --sort athlete
```

Manual corrections:

```bash
running-contacts contacts add-alias --contact-id 691 --alias "Jean Noel"
running-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 691
running-contacts matching reject --dataset liege-15k-2026 --result-id 5678 --note "homonyme"
running-contacts matching list-reviews --dataset liege-15k-2026
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
running-contacts-gui
```
