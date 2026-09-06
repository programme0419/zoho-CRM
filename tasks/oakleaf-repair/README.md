# oakleaf-repair

Repair a shipping Oakleaf embedded key-value store so it matches its
on-disk format and operational spec.

## What the agent is given

- `/app/oakleaf` — WAL, SSTables, manifest, CLI, and a shipping snapshot
  that does not implement every FORMAT.md rule correctly.
- `/app/oakleaf/FORMAT.md` — the normative format and operations.
- `/app/oakleaf/samples/simple` — a production directory written by a
  spec-accurate engine. It only exercises the paths that still work.

## The deliverable

A repaired `/app/oakleaf` such that `python -m oakleaf --db <dir> ...`
matches FORMAT.md for every directory, and every directory this engine
writes remains readable by a spec-accurate reader.

## Difficulty explanation

Production storage-engine repair. Several interacting divergences
(scan bounds, newest-wins, tombstones, empty PUT, signed compares,
compact) are invisible on the sample directory. A format-changing
rewrite fails verifier reopen.

## Solution explanation

Replace the snapshot with a spec-accurate engine: unsigned newest-wins,
half-open memcmp scans, always-written tombstones, empty live PUTs,
compact drops newest-tombstone keys, next_seq is preserved.

## Verification explanation

Separate verifier, twelve hidden cases, plus an independent oracle
reopen of directories the agent wrote. Reward is 1 only if every CLI
line and every reopen matches.

## Relevant experience

Embedded key-value store repair (WAL, SST, unsigned key order). Oakleaf
was implemented against its format note, then the shipping snapshot was
regressed in ways that still open the sample.
