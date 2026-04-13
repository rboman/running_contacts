# Handoff Notes

Read this file first when resuming work on `running_contacts` in a later Codex session.

## Current State

- `contacts` is implemented and syncs one Google account into `data/contacts.sqlite3`.
- `race_results` is implemented for ACN Timing / Chronorace and stores local datasets in `data/race_results.sqlite3`.
- `matching` is implemented with:
  - exact and fuzzy matching,
  - contact aliases,
  - race dataset aliases,
  - manual review commands (`accept`, `reject`, `clear-review`, `list-reviews`),
  - sorted and filtered listing (`matching list`).

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

- another targeted cleanup pass on likely false negatives for `liege-15k-2026`

Good ways to do that:

1. inspect one patronymic cluster at a time (`noel`, `halain`, `denoel`, etc.)
2. add reusable contact aliases when a naming variant is stable
3. use manual reviews only for one-off decisions
4. rerun `matching run --dataset liege-15k-2026` after each small batch
