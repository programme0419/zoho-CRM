# Evaluation record

Source of truth for CI defaults: Terminal-Bench `docs/TASK_REVIEW_AUTOMATION.md` and `.github/harbor-run-defaults.yml` (copied here as [`docs/harbor-run-defaults.yml`](docs/harbor-run-defaults.yml), retrieved 2026-09-04).

Default `/run` agents:

| Agent        | Model                    | kwargs                         | env                                      | trials |
|--------------|--------------------------|--------------------------------|------------------------------------------|--------|
| claude-code  | anthropic/claude-opus-5  | reasoning_effort=max           | CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000     | 3      |
| codex        | openai/gpt-5.6-sol       | reasoning_effort=xhigh         | —                                        | 3      |

`/cheat` uses the same two configs, one trial each, with [`docs/hack-trial-prompt.md`](docs/hack-trial-prompt.md) appended to the instruction.

Environment backend used here: `docker` (CI default is `modal`; docker is the documented override for local validation).

Harbor version: `0.22.0`.

## Automated checks

### Static checks

Command:

```bash
bash scripts/run_static_checks.sh tasks/scan-margin
```

Result: **PASS** (all `scripts/checks/check-*.sh`).

| Check | Result |
|-------|--------|
| check-allow-internet | PASS |
| check-canary | PASS |
| check-compose-host-binds | PASS |
| check-dockerfile-platform | PASS |
| check-dockerfile-references | PASS |
| check-dockerfile-sanity | PASS |
| check-gpu-types | PASS |
| check-instruction-suffix | PASS |
| check-no-allow-internet-true | PASS |
| check-nproc | PASS |
| check-pip-pinning | PASS |
| check-pytest-version | PASS |
| check-separate-verifier | PASS |
| check-task-absolute-path | PASS |
| check-task-fields | PASS |
| check-task-package-name | PASS |
| check-task-slug | PASS |
| check-task-timeout | PASS |
| check-test-file-references | PASS |
| check-test-sh-sanity | PASS |
| check-trial-network-fetch | PASS |
| check-verifier-tooling-baked | PASS |

Implementation-rubric review (`harbor check tasks/scan-margin -r docs/task-implementation.toml`) needs an LLM judge key (`ANTHROPIC_API_KEY`). It was not run in this sandbox for that reason. The task was written against that rubric: separate verifier, baked pytest, hidden oracle, unprivileged CLI execution, CTRF, binary reward, human-written instruction, no `allow_internet` pin.

### Docker build / oracle / nop

```bash
export DOCKER_BUILDKIT=0
harbor run -p tasks/scan-margin --agent oracle --env docker --yes -o results/oracle
harbor run -p tasks/scan-margin --agent nop    --env docker --yes -o results/nop
```

| Check | Reward | Errors | Evidence |
|-------|--------|--------|----------|
| Docker build (env + verifier images) | built | 0 | implicit in oracle/nop runs |
| Oracle validation | **1.0** | 0 | [results/summaries/oracle.json](results/summaries/oracle.json) |
| Nop validation | **0.0** | 0 | [results/summaries/nop.json](results/summaries/nop.json) |

Oracle job id `4bdde259-3ea5-4a3f-b44c-d7fd4d58e12a` (2026-09-04T16:36:52Z), 1/1 reward 1.0, 40s.
Nop job id `023f962e-fc80-46ec-bac4-c6de151cfe0c` (2026-09-04T16:37:39Z), 1/1 reward 0.0, 30s.

## Standard agent trials (`/run`)

Commands (CI defaults, three attempts each):

```bash
harbor run -p tasks/scan-margin \
  --agent codex --model openai/gpt-5.6-sol \
  --env docker --yes -k 3 \
  --ae CODEX_FORCE_AUTH_JSON=1 --ak reasoning_effort=xhigh \
  -o results/run-codex

harbor run -p tasks/scan-margin \
  --agent claude-code --model anthropic/claude-opus-5 \
  --env docker --yes -k 3 \
  --ae CLAUDE_FORCE_OAUTH=1 \
  --ae CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 \
  --ak reasoning_effort=max \
  -o results/run-claude
```

Wrapper: `bash scripts/run_trials.sh run-codex` and `run-claude`.

| Config | Trial | Reward | Error? | Notes |
|--------|-------|--------|--------|-------|
| codex / openai/gpt-5.6-sol / xhigh | 1 | *pending subscription login* | | |
| codex / openai/gpt-5.6-sol / xhigh | 2 | *pending* | | |
| codex / openai/gpt-5.6-sol / xhigh | 3 | *pending* | | |
| claude-code / anthropic/claude-opus-5 / max | 1 | *pending subscription login* | | |
| claude-code / anthropic/claude-opus-5 / max | 2 | *pending* | | |
| claude-code / anthropic/claude-opus-5 / max | 3 | *pending* | | |

Requirement: all six completed trials fail the verifier. Timeouts, rate limits, and infrastructure errors will be retried and not counted.

## Adversarial trials (`/cheat`)

```bash
bash scripts/run_trials.sh cheat-codex
bash scripts/run_trials.sh cheat-claude
```

| Config | Reward | Requirement |
|--------|--------|-------------|
| codex / openai/gpt-5.6-sol / xhigh | *pending* | must be 0.0 |
| claude-code / anthropic/claude-opus-5 / max | *pending* | must be 0.0 |

Anti-cheat surface the verifier actually closes:

- Separate verifier image; `/tests` is `chmod 700` before the agent CLI runs.
- Agent CLI runs as `nobody` with `--no-new-privs`; `/logs/verifier` is root-only `700`.
- Hidden books live only in the verifier image.
- Ground-truth is recomputed by `tests/oracle.py`, not compared to a leaked golden file in the agent image.
- The sample book is already solved by the starter; nop still scores 0 because the CLI is never run and hidden books fail.

## Failure analysis (design, pre-trial)

The intended failure is **partial implementation of a house methodology**, not formatting.

The starter already emits a correct report for `/app/hsm/data/portfolio.json` (two long CL futures → $5,000, worst scenario 13). An agent that treats that file as the test suite, or that ports SPAN defaults (0.35 extreme cover, ATM delta for spreading, SOM before credits, credits for same-sign energy books), will match the sample and fail the hidden books:

| Hidden book | Isolates |
|-------------|----------|
| `som_otm` | moneyness-scaled SOM on short OTM calls |
| `calendar` | greedy intra-month charge with √(d/365) |
| `crack` | offsetting CL/HO intercommodity credit |
| `nov_long` | NOV cancels long-option scan; component fields still checked |
| `fx_equity` | EUR→USD after native combine |
| `mixed_opt` | futures + short OTM puts, vol scenarios |
| `ics_priority` | priority 1 consumes CL vs HO before CL vs RB |
| `netting` | duplicate instrument_id rows |
| `multi_cc` | ES + CL calendar + GX option together |
| `vol_mix` | mixed option/futures vol shocks |

A cheat agent cannot write `reward.txt` (root-only, other container), cannot read `/tests` (mode 700 while the CLI runs), and cannot hardcode the sample: `som_otm` and `sample` totals must differ, and ten other books must match the oracle.

Once `/run` and `/cheat` jobs finish, this section will be updated with per-trial traces (`harbor analyze`) and whether failures matched this crux.
