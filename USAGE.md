# Usage Guide

This file is the practical help for day-to-day use of `match-my-contacts`.

If you come back in a later Codex session, read `HANDOFF.md` first.

## Data directory

The application now uses a local machine config file:

```bash
~/.config/match_my_contacts/config.toml
```

On Windows, the equivalent location is:

```powershell
$env:APPDATA\match_my_contacts\config.toml
```

This file is auto-created on first CLI or GUI launch and contains:

```toml
data_dir = "/absolute/path/to/match_my_contacts_data"
credentials_path = "/absolute/path/to/credentials.json"
```

All default local paths derive from that directory:

- `contacts.sqlite3`
- `race_results.sqlite3`
- `google/token.json`
- `raw/acn_timing/`
- `exports/`

This makes it easy to point several machines to the same Dropbox-backed working directory, as long as only one machine uses the SQLite files at a time.

Inspect the active config and resolved paths:

```bash
match-my-contacts config show
```

## 1. Manage contacts

If `credentials.json` is at the project root:

```bash
match-my-contacts contacts sync
match-my-contacts contacts sync-google
```

Useful commands:

```bash
match-my-contacts contacts list
match-my-contacts contacts list --query noel
match-my-contacts contacts list --source google_people
match-my-contacts contacts list-sources
match-my-contacts contacts import-google-csv --csv-path /path/to/google-contacts.csv
match-my-contacts contacts empty-db
match-my-contacts contacts vacuum-db
match-my-contacts contacts export-json --output data/exports/contacts.json
```

The contact ID shown by `contacts list` is useful for manual aliasing and review.

Current source model:

- `google_people` is a syncable API source
- `google_contacts_csv` is a snapshot import source
- sources remain separated in the same SQLite database
- a Google resync only affects Google API contacts for its account slot
- a CSV reimport only affects CSV-imported contacts for its account slot
- `contacts empty-db` clears the contacts DB and matching reviews, but keeps race datasets/results
- `contacts vacuum-db` runs SQLite `VACUUM` on `contacts.sqlite3` to compact the file on disk

## GUI locale

Install the optional desktop GUI dependencies:

```bash
pip install -e .[gui]
```

Python `3.10+` is supported.

On a fresh Windows virtualenv, upgrading the packaging tools first usually makes dependency resolution much faster:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

On Linux/X11, install the Qt system dependency if needed:

```bash
sudo apt install libxcb-cursor0
```

Launch the GUI:

```bash
match-my-contacts-gui
```

The GUI is intentionally simple, but already useful:

- it keeps the CLI unchanged,
- it auto-loads local contacts when the SQLite cache already exists,
- it syncs Google Contacts and imports Google Contacts CSV exports into the same local database,
- it shows a modal success or error dialog after `Sync Google`,
- it can empty the local contacts database after an explicit confirmation,
- it can run SQLite `VACUUM` on the local contacts database,
- it loads contacts and exports them to JSON,
- it lets you choose the visible contact columns, including the optional source column,
- it opens a detailed contact dialog on double-click, including source metadata and raw JSON,
- it fetches ACN races, lists datasets, shows results, and adds dataset aliases,
- it runs matching, applies filters, and exports the visible CSV selection,
- it shows and edits the local configuration, including the shared data directory and optional `credentials.json` path,
- it exposes a small `Help` menu with `About` and `Credits`,
- it still leaves manual review workflows to the CLI for now.

Recommended daily GUI workflow:

```bash
match-my-contacts-gui
```

Then:

- review the auto-loaded contacts table or click `Load contacts` if needed,
- use `Sync Google` when you want to refresh the API-backed Google contacts,
- use `Import Google CSV` with a real Google Contacts export when you want a local snapshot without the API sync flow,
- use `Empty DB...` when you want to wipe the local contacts cache and matching reviews for debugging,
- use `VACUUM DB` when you want SQLite to compact `contacts.sqlite3` on disk,
- use `Columns...` to reduce the contacts table to the fields you care about, including source visibility,
- double-click a contact row to inspect the full stored payload, DB metadata, and source metadata,
- fetch a race from its ACN URL,
- add a short alias to the dataset,
- run matching on that alias,
- refine the visible list with filters,
- export the filtered CSV when needed.

## Dropbox migration

1. launch the CLI or GUI once to auto-create the local config file
2. edit `data_dir` so it points to your Dropbox folder
3. copy the current `data/` contents into that shared folder
4. restart the CLI or GUI
5. confirm that contacts, race datasets, aliases, and exports are visible

Important:

- do not use the same shared SQLite files simultaneously on two machines
- wait for Dropbox sync to finish before switching machines
- if Dropbox creates conflict copies, inspect those files before continuing

## 2. Import a race

Fetch an ACN Timing race once and keep it locally:

```bash
match-my-contacts race-results fetch-acn --url 'https://www.acn-timing.com/?lng=FR#/events/2157220339092161/ctx/20260412_liege/generic/197994_1/home/LIVE1'
```

Inspect local races:

```bash
match-my-contacts race-results list-datasets
match-my-contacts race-results list-aliases
match-my-contacts race-results list-results --dataset 1 --query ucci
```

You can assign a short alias to a race:

```bash
match-my-contacts race-results add-alias --dataset-id 1 --alias liege-15k-2026
match-my-contacts race-results list-aliases
```

After that, use `--dataset liege-15k-2026` instead of `--dataset-id 1`.

## 3. Run matching

Summary:

```bash
match-my-contacts matching run --dataset liege-15k-2026
match-my-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 30
```

List matches with filters and sorting:

```bash
match-my-contacts matching list --dataset liege-15k-2026 --sort time
match-my-contacts matching list --dataset liege-15k-2026 --sort athlete
match-my-contacts matching list --dataset liege-15k-2026 --sort contact
match-my-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE
match-my-contacts matching list --dataset liege-15k-2026 --status ambiguous
match-my-contacts matching list --dataset liege-15k-2026 --name-query noel
match-my-contacts matching list --dataset liege-15k-2026 --category SEH
match-my-contacts matching list --dataset liege-15k-2026 --reviewed-only
```

Export the same filtered view:

```bash
match-my-contacts matching export-csv --dataset liege-15k-2026 --team TEAMULIEGE --sort time --output data/exports/teamuliege_matches.csv
```

## 4. Correct false negatives or false positives

### Add a reusable alias to a contact

Use this when a person appears often under a variant of their name:

```bash
match-my-contacts contacts add-alias --contact-id 691 --alias "Jean Noel"
match-my-contacts contacts list-aliases --contact-id 691
```

### Force or reject one result manually

Use this when a single result needs a manual decision:

```bash
match-my-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 691
match-my-contacts matching reject --dataset liege-15k-2026 --result-id 5678 --note "homonyme"
match-my-contacts matching list-reviews --dataset liege-15k-2026
match-my-contacts matching clear-review --dataset liege-15k-2026 --result-id 1234
```

## 5. Leave and resume later in Codex

Interactive Codex sessions are resumable locally.

Resume the last interactive session:

```bash
codex resume --last
```

Open the session picker:

```bash
codex resume
```

If you want the next session to keep the repository context even if you do not resume the exact same interactive session:

```bash
sed -n '1,220p' HANDOFF.md
sed -n '1,260p' README.md
sed -n '1,320p' USAGE.md
```

To preserve code state as well as conversation state, commit your work or at least keep the working tree unchanged before leaving.

## 6. Typical workflows

### New race

```bash
match-my-contacts contacts sync-google
match-my-contacts race-results fetch-acn --url '...'
match-my-contacts race-results add-alias --dataset-id 1 --alias liege-15k-2026
match-my-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 30
```

### Import snapshot contacts from CSV

```bash
match-my-contacts contacts import-google-csv --csv-path /path/to/google-contacts.csv
match-my-contacts contacts list-sources
match-my-contacts contacts list --source google_contacts_csv
```

### Explore one team

```bash
match-my-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE --sort time
```

### Clean up ambiguous cases

```bash
match-my-contacts matching list --dataset liege-15k-2026 --status ambiguous
match-my-contacts contacts list --query noel
match-my-contacts contacts add-alias --contact-id 691 --alias "Jean Noel"
match-my-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 691
```

## Current priority

The current matching quality is considered good enough for now. The next development priority is to extend the PySide6 GUI toward review workflows rather than changing the matching engine itself.

## GUI updates

Recent GUI additions:

- local contacts now auto-load on startup when the contacts SQLite file already exists
- `Contacts` now supports both `Sync Google` and `Import Google CSV`
- the contacts table now supports persistent visible-column preferences via Qt settings
- the optional source column exposes the contact origin directly in the table
- double-clicking a contact row opens a read-only details dialog with DB metadata, source metadata, and raw JSON
- the desktop window now exposes a small `Help` menu with `About` and `Credits`

Current CSV assumption:

- the GUI import only targets the real Google Contacts CSV export format for now
- no generic CSV mapping wizard has been added yet
