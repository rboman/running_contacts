# Usage Guide

This file is the practical help for day-to-day use of `running_contacts`.

If you come back in a later Codex session, read `HANDOFF.md` first.

## 1. Sync contacts

If `credentials.json` is at the repository root:

```bash
running-contacts contacts sync
```

Useful commands:

```bash
running-contacts contacts list
running-contacts contacts list --query noel
running-contacts contacts export-json --output data/exports/contacts.json
```

The contact ID shown by `contacts list` is useful for manual aliasing and review.

## GUI locale

Install the optional desktop GUI dependencies:

```bash
pip install -e .[gui]
```

On Linux/X11, install the Qt system dependency if needed:

```bash
sudo apt install libxcb-cursor0
```

Launch the GUI:

```bash
running-contacts-gui
```

The GUI is intentionally simple, but already useful:

- it keeps the CLI unchanged,
- it loads contacts and exports them to JSON,
- it fetches ACN races, lists datasets, shows results, and adds dataset aliases,
- it runs matching, applies filters, and exports the visible CSV selection,
- it still leaves Google sync and manual review workflows to the CLI for now.

Recommended daily GUI workflow:

```bash
running-contacts-gui
```

Then:

- load contacts when you want to inspect the local cache,
- fetch a race from its ACN URL,
- add a short alias to the dataset,
- run matching on that alias,
- refine the visible list with filters,
- export the filtered CSV when needed.

## 2. Import a race

Fetch an ACN Timing race once and keep it locally:

```bash
running-contacts race-results fetch-acn --url 'https://www.acn-timing.com/?lng=FR#/events/2157220339092161/ctx/20260412_liege/generic/197994_1/home/LIVE1'
```

Inspect local races:

```bash
running-contacts race-results list-datasets
running-contacts race-results list-aliases
running-contacts race-results list-results --dataset 1 --query ucci
```

You can assign a short alias to a race:

```bash
running-contacts race-results add-alias --dataset-id 1 --alias liege-15k-2026
running-contacts race-results list-aliases
```

After that, use `--dataset liege-15k-2026` instead of `--dataset-id 1`.

## 3. Run matching

Summary:

```bash
running-contacts matching run --dataset liege-15k-2026
running-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 30
```

List matches with filters and sorting:

```bash
running-contacts matching list --dataset liege-15k-2026 --sort time
running-contacts matching list --dataset liege-15k-2026 --sort athlete
running-contacts matching list --dataset liege-15k-2026 --sort contact
running-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE
running-contacts matching list --dataset liege-15k-2026 --status ambiguous
running-contacts matching list --dataset liege-15k-2026 --name-query noel
running-contacts matching list --dataset liege-15k-2026 --category SEH
running-contacts matching list --dataset liege-15k-2026 --reviewed-only
```

Export the same filtered view:

```bash
running-contacts matching export-csv --dataset liege-15k-2026 --team TEAMULIEGE --sort time --output data/exports/teamuliege_matches.csv
```

## 4. Correct false negatives or false positives

### Add a reusable alias to a contact

Use this when a person appears often under a variant of their name:

```bash
running-contacts contacts add-alias --contact-id 691 --alias "Jean Noel"
running-contacts contacts list-aliases --contact-id 691
```

### Force or reject one result manually

Use this when a single result needs a manual decision:

```bash
running-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 691
running-contacts matching reject --dataset liege-15k-2026 --result-id 5678 --note "homonyme"
running-contacts matching list-reviews --dataset liege-15k-2026
running-contacts matching clear-review --dataset liege-15k-2026 --result-id 1234
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
running-contacts contacts sync
running-contacts race-results fetch-acn --url '...'
running-contacts race-results add-alias --dataset-id 1 --alias liege-15k-2026
running-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 30
```

### Explore one team

```bash
running-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE --sort time
```

### Clean up ambiguous cases

```bash
running-contacts matching list --dataset liege-15k-2026 --status ambiguous
running-contacts contacts list --query noel
running-contacts contacts add-alias --contact-id 691 --alias "Jean Noel"
running-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 691
```

## Current priority

The current matching quality is considered good enough for now. The next development priority is to extend the PySide6 GUI toward review workflows rather than changing the matching engine itself.
