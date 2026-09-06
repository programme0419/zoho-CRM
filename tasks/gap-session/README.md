# gap-session

Repair an event-time session-window pipeline whose defects only appear
when events, watermarks, and session state interact across time.

## What the agent is given

- `/app/pipeline` — shipping snapshot (plausible, well-commented, wrong)
- `/app/pipeline/design.md` — the contract
- `/app/pipeline/samples/inorder.jsonl` — one in-order single-source tape
  that does not trigger the incident

## The deliverable

`python -m pipeline --events IN --gap G --lateness L --output OUT` must
match the design for every stream, not just the sample.

## Difficulty explanation

On-call streaming incident. Coupled defects (min vs max watermark,
inclusive gap, merge totals, emit bound, same-timestamp, late open).
A one-symptom patch fails the other histories.

## Solution explanation

Implement the design literally: min watermark, inclusive join, distinct
same-timestamp events, late events join-only, merge sums, emit only when
`W > last + G`, flush leftovers at end-of-stream.

## Verification explanation

Separate verifier, sample plus seven hidden streams. Reward is 1 only if
every record matches on key/start/last/count/total.

## Relevant experience

Event-time session windows and late-data / watermark incidents. The
sessionizer was implemented against the design, then the snapshot was
regressed in coupled ways that still pass the in-order sample.
