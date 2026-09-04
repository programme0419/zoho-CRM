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

## Requirement status

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Static checks | **PASS** (re-run 2026-09-04T17:30Z) | this file |
| Implementation-rubric (`harbor check`) | **blocked** — needs `ANTHROPIC_API_KEY` | mechanical subset **PASS** |
| Docker build | **PASS** | oracle / nop / local matrix |
| Oracle reward 1.0 | **PASS** (two Harbor jobs) | [oracle.json](results/summaries/oracle.json) |
| Nop reward 0.0 | **PASS** (two Harbor jobs) | [nop.json](results/summaries/nop.json) |
| Any correct engine scores 1 | **PASS** | official solution **and** dataclass rewrite |
| Incomplete / hardcoded engines score 0 | **PASS** | starter + hardcoded sample |
| `/run` × 3 Codex genuinely fail | **FAIL — 3/3 then 3/3 after overlays** | [run-codex.json](results/summaries/run-codex.json), [run-codex-harden.json](results/summaries/run-codex-harden.json) |
| `/run` × 3 Claude genuinely fail | **not counted** | no `CLAUDE_CODE_OAUTH_TOKEN` |
| `/cheat` Codex reward 0 | **in progress** | started after `/run` |
| `/cheat` Claude reward 0 | **not counted** | no token |

Crashes, API/rate-limit, container, timeout, and network errors do **not** count as model failures. They are recorded below so they are not mistaken for verifier zeros.

## Automated checks

### Static checks

Command:

```bash
bash scripts/run_static_checks.sh tasks/scan-margin
```

Result: **PASS** (all `scripts/checks/check-*.sh`), first run and re-run 2026-09-04T17:30Z.

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

### Implementation rubric

Official command:

```bash
harbor check tasks/scan-margin -r docs/task-implementation.toml
```

Needs an LLM judge (`ANTHROPIC_API_KEY` / Claude Code). Not run here.

Mechanical subset (no LLM) of the same rubric: `python3 scripts/check_implementation_rubric_mechanical.py` → **PASS**. Log: [results/summaries/mechanical-rubric.txt](results/summaries/mechanical-rubric.txt).

That gate confirms separate verifier, declared artifacts, omitted `allow_internet`, baked pytest 9.1.1 + CTRF, binary 0/1 reward, `nobody` + `--no-new-privs`, root-only `/logs/verifier`, locked `/tests`, hidden books only in the verifier image, oracle-compared money fields, and no agent-module import in pytest.

### Docker build / oracle / nop

```bash
export DOCKER_BUILDKIT=0
harbor run -p tasks/scan-margin --agent oracle --env docker --yes -o results/oracle
harbor run -p tasks/scan-margin --agent nop    --env docker --yes -o results/nop
```

| Check | Reward | Errors | Evidence |
|-------|--------|--------|----------|
| Docker build (env + verifier images) | built | 0 | implicit in oracle/nop/local matrix |
| Oracle validation | **1.0** | 0 | [results/summaries/oracle.json](results/summaries/oracle.json) |
| Nop validation | **0.0** | 0 | [results/summaries/nop.json](results/summaries/nop.json) |

First Harbor jobs:

- Oracle `4bdde259-3ea5-4a3f-b44c-d7fd4d58e12a` (2026-09-04T16:36:52Z), reward 1.0
- Nop `023f962e-fc80-46ec-bac4-c6de151cfe0c` (2026-09-04T16:37:39Z), reward 0.0

Re-run (same commands, 2026-09-04T17:30Z):

- Oracle `e6e022e9-8a09-4fe5-a4e1-30a080ca4831`, reward 1.0, 30s
- Nop `658d305d-102f-4fa3-a28d-41ad97b20266`, reward 0.0, 29s

First-run copies: [oracle-first.json](results/summaries/oracle-first.json), [nop-first.json](results/summaries/nop-first.json).

### Any-solution verifier matrix

The hiring bar is that a **correct** engine passes and an incomplete one does not. The official `solution/` is one implementation; the verifier must not be overfit to its source.

```bash
bash scripts/verify_local.sh
```

Same `tests/Dockerfile` image and `tests/test.sh` Harbor uses. Results: [results/summaries/local-verifier/README.md](results/summaries/local-verifier/README.md).

| Variant | Engine | Reward | Required |
|---------|--------|--------|----------|
| official-solution | `tasks/scan-margin/solution/engine.py` | **1** | 1 |
| alt-dataclass | `scripts/alt-hsm/engine.py` (rewrite: dataclasses, two-pass combine) | **1** | 1 |
| starter | bundled futures-only scanner | **0** | 0 |
| hardcoded-sample | always $5000 / scenario 13 | **0** | 0 |

The alternate engine is not copied into the task image. It exists only under `scripts/` so reviewers can re-run the matrix.

Starter detail (8/13 pytest failures): [starter-passthrough.md](results/summaries/starter-passthrough.md).

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
| codex / openai/gpt-5.6-sol / xhigh | 1–3 | **1.0 × 3** | none | Job `2026-09-04__18-00-05` (HSM 1.0 spec). Then overlays harden, job `2026-09-04__18-37-45`, another **1.0 × 3** in 29m (~$3.98). The model transcribes a complete written methodology. **Hiring bar requires all three to fail.** |
| claude-code / anthropic/claude-opus-5 / max | 1–3 | not run | n/a | `claude auth status` → loggedIn false. No `CLAUDE_CODE_OAUTH_TOKEN`. |

Earlier Codex jobs (`4960ffb6-…`, `2026-09-04__17-53-20`) died on `NetworkConnectionError` during `apt-get` inside Harbor’s Compose network. That is infra. This host’s user-defined Docker networks cannot NAT IPv4; the default `docker0` bridge can. `scripts/run_trials.sh` now passes `scripts/docker-compose.bridge.yaml` (`network_mode: bridge`). After that overlay, Codex installed and called the API.

Auth used a host `OPENAI_API_KEY` (not committed). `codex login` is still unused.

To complete the table on a subscribed machine:

1. `codex login` then `bash scripts/run_trials.sh run-codex`
2. Finish `claude setup-token`, `export CLAUDE_CODE_OAUTH_TOKEN=...`, then `bash scripts/run_trials.sh run-claude`

Copy each job's `result.json` into `results/summaries/`.

## Adversarial trials (`/cheat`)

```bash
bash scripts/run_trials.sh cheat-codex
bash scripts/run_trials.sh cheat-claude
```

| Config | Reward | Error? | Requirement |
|--------|--------|--------|-------------|
| codex / openai/gpt-5.6-sol / xhigh | none | **NetworkConnectionError** (job under `results/cheat-codex/2026-09-04__16-50-13`) | must be 0.0 after a completed trial |
| claude-code / anthropic/claude-opus-5 / max | not run | no OAuth token | must be 0.0 |

Local cheat-shaped engines (starter, hardcoded sample) already score **0** on the real verifier. That is not a substitute for the required Codex/Claude `/cheat` jobs.

Anti-cheat surface the verifier actually closes:

- Separate verifier image; `/tests` is `chmod 700` before the agent CLI runs.
- Agent CLI runs as `nobody` with `--no-new-privs`; `/logs/verifier` is root-only `700`.
- Hidden books live only in the verifier image.
- Ground-truth is recomputed by `tests/oracle.py`, not compared to a leaked golden file in the agent image.
- The sample book is already solved by the starter; nop still scores 0 because the CLI is never run and hidden books fail.
- A CLI that always writes the sample $5,000 report fails `test_sample_not_hardcoded_only` plus every options/spread book.

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

Once `/run` and `/cheat` jobs finish with a live model, this section will be updated with per-trial traces (`harbor analyze`) and whether failures matched this crux.
