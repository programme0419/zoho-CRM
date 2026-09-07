# nds-desk

Repair a house Next-Day Settlement desk whose defects only appear when
calendars, tenors, day-count conventions, and schedule rolls interact.

## What the agent is given

- `/app/nds` — shipping snapshot (plausible, well-commented, wrong)
- `/app/nds/HANDBOOK.md`, `HOLSPEC.md`, `ERRATA.md` — the contract
- `/app/nds/cals/*.hol` — production HOL1 packs
- `/app/nds/samples/smoke.json` — one weekday tape that does not
  trigger the incident

## The deliverable

`python -m nds --batch IN.json --output OUT.json` must match the
handbook for every book, not just the sample.

## Difficulty explanation

On-call rates-desk incident. Coupled defects (0-origin HOL1 months,
per-pack weekend masks, half-sessions, intersecting joined calendars,
ON vs 1D, IMM Wednesday, EOM month-add, H30, half-away rounding,
unadjusted accrual, long stubs). A one-symptom patch fails the other
books.

## Solution explanation

Implement the handbook literally: 0-origin HOL1 months, pack weekend
masks, settle-closed half-sessions, intersection joins, settlement-day
ON/TN/SN, third-Wednesday IMM, EOM month-add without day spill, H30
EOM→30, half-away money, unadjusted accrual, long-stub collapse.

## Verification explanation

Separate verifier, smoke plus eleven hidden books. Reward is 1 only if
every job matches on dates, day counts, fractions, and amounts.

## Relevant experience

Rates or futures date libraries and production calendar-pack incidents.
The desk was implemented against the handbook, then the snapshot was
regressed in coupled ways that still pass a weekday smoke tape.
