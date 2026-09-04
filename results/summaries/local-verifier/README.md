# Local verifier matrix

Date: 2026-09-04T17:33:48Z

Real `tests/Dockerfile` verifier, same `test.sh` Harbor uses.

| Variant | Engine | Reward | Required |
|---------|--------|--------|----------|
| official-solution | `tasks/scan-margin/solution/engine.py` | 1 | 1 |
| alt-dataclass | `scripts/alt-hsm/engine.py` | 1 | 1 |
| starter | bundled futures-only scanner | 0 | 0 |
| hardcoded-sample | always $5000 / scenario 13 | 0 | 0 |
