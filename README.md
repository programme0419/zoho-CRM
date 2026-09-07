# NDS desk — Terminal-Bench 3 task

**This is the submission repo.** Send reviewers this GitHub URL:

https://github.com/programme0419/Klavis-test

Task path: [`tasks/nds-desk`](tasks/nds-desk). Harbor scan will see only that task.

Original Terminal-Bench 3 task: repair a **house Next-Day Settlement (NDS) desk** — calendars, tenors, IMM dates, day-count conventions, and coupon schedules. The shipping snapshot already runs a weekday smoke batch. The contract is the handbook, not the comments in the Python tree.

This repository is a self-contained submission. It is not a PR to the Terminal-Bench project.

**Author-side checks do not need a paid API key.** Static checks, `/validate` (oracle + nop), and the local verifier matrix are Docker-only. CI `/run` and `/cheat` use subscription login (`codex login`, `claude setup-token`), matching [docs/harbor-run-defaults.yml](docs/harbor-run-defaults.yml).

## Task

Path: [`tasks/nds-desk`](tasks/nds-desk)

The agent is dropped into `/app/nds` with `HANDBOOK.md`, `HOLSPEC.md`, `ERRATA.md`, production HOL1 holiday packs, and a starter that already handles a weekday smoke tape. A correct engine has to decode 0-origin HOL1 months, honour per-pack weekend masks and half-sessions, intersect joined calendars, treat `ON`/`TN`/`SN` as settlement-day steps, take IMM as the third Wednesday, snap EOM month-add without spilling into the next month, compute house 30/360 (`H30`), round half away from zero, and accrue coupons on the unadjusted roll.

The verifier never grades the smoke batch alone. After the agent finishes, a separate verifier container runs the submitted CLI as `nobody` on twelve hidden books.

## Layout

```
tasks/nds-desk/
  instruction.md
  task.toml
  README.md
  environment/              # agent image
  solution/                 # oracle solution
  tests/                    # separate verifier image, hidden books
docs/
  harbor-run-defaults.yml   # TB3 CI /run and /cheat defaults
  hack-trial-prompt.md
  task-implementation.toml
scripts/checks/
scripts/run_static_checks.sh
scripts/run_trials.sh
scripts/nds/                # local verifier + mechanical rubric
results/summaries/
archive/                    # earlier drafts, not the submission
```

## Run locally

Needs Docker, Docker Compose v2, and [Harbor](https://github.com/laude-institute/harbor):

```bash
uv tool install harbor
```

Nested-container hosts (overlay-on-overlay) should run the daemon with `"storage-driver": "vfs"` and `DOCKER_BUILDKIT=0`.

### Author checks (no API key)

```bash
export DOCKER_BUILDKIT=0
bash scripts/run_static_checks.sh tasks/nds-desk
TASK=tasks/nds-desk bash scripts/run_trials.sh oracle   # must be 1.0
TASK=tasks/nds-desk bash scripts/run_trials.sh nop      # must be 0.0
bash scripts/nds/verify_local.sh                        # solution=1, shipping=0
python3 scripts/nds/check_mechanical.py
```

### Evaluator `/run` and `/cheat` (subscription login, not a paid key)

Three `/run` trials each, matching [docs/harbor-run-defaults.yml](docs/harbor-run-defaults.yml):

```bash
# Codex: `codex login` then:
TASK=tasks/nds-desk bash scripts/run_trials.sh run-codex

# Claude Code: `claude setup-token` then:
TASK=tasks/nds-desk bash scripts/run_trials.sh run-claude
```

`/cheat` appends [docs/hack-trial-prompt.md](docs/hack-trial-prompt.md):

```bash
TASK=tasks/nds-desk bash scripts/run_trials.sh cheat-codex
TASK=tasks/nds-desk bash scripts/run_trials.sh cheat-claude
```

Crashes, rate limits, container failures, and timeouts are infra, not model results.

## Recorded author-side results

| Check | Result |
| --- | --- |
| Static checks | PASS |
| Oracle | 1.0 |
| Nop | 0.0 |
| Local verifier (solution / shipping) | 1 / 0 |
| Mechanical rubric | PASS |

See [EVALUATION.md](EVALUATION.md) for Harbor `result.json` pointers.
