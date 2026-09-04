# House Scan Margin — Terminal-Bench 3 task

Original Terminal-Bench 3 task: implement a **house scanning-range initial-margin engine** (HSM) for a mixed futures-and-options clearing book. HSM is specified in full in the task; it is not CME SPAN.

This repository is a self-contained submission. It is not a PR to the Terminal-Bench project.

## Task

Path: [`tasks/scan-margin`](tasks/scan-margin)

The agent is dropped into `/app/hsm` with a methodology, an HSMJ journal spec, schemas, market/config data, one sample tape, and a starter that already margins that v1 sample. The starter is a v1-only blotter plus a futures-only scanner. A correct engine has to decode production journals and implement the 16-scenario array, house overlays, and FX conversion — in that order.

The verifier never grades the sample book alone. After the agent finishes, a separate verifier container runs the submitted CLI as `nobody` on the sample tape plus sixteen hidden HSMJ books and compares each report to an independent oracle.

## Layout

```
tasks/scan-margin/
  instruction.md
  task.toml
  README.md                 # reviewer-facing explanations
  environment/              # agent image
  solution/                 # oracle solution
  tests/                    # separate verifier image, oracle, hidden books
docs/
  harbor-run-defaults.yml   # TB3 CI /run and /cheat defaults (copied)
  hack-trial-prompt.md      # TB3 /cheat prompt (copied)
  task-implementation.toml  # TB3 implementation rubric (copied)
scripts/checks/             # TB3 static check scripts (copied)
scripts/run_static_checks.sh
scripts/run_trials.sh
results/summaries/          # recorded Harbor result.json files
```

## Run locally

Needs Docker, Docker Compose v2, and [Harbor](https://github.com/laude-institute/harbor):

```bash
uv tool install harbor
```

Nested-container hosts (overlay-on-overlay) should run the daemon with `"storage-driver": "vfs"` and `DOCKER_BUILDKIT=0`.

### Static checks (CI)

```bash
bash scripts/run_static_checks.sh tasks/scan-margin
```

### Oracle and nop (CI validation)

```bash
export DOCKER_BUILDKIT=0
harbor run -p tasks/scan-margin --agent oracle --env docker --yes -o results/oracle
harbor run -p tasks/scan-margin --agent nop    --env docker --yes -o results/nop
```

Oracle must report reward `1.0`. Nop must report reward `0.0`.

### Any correct engine (local verifier matrix)

```bash
export DOCKER_BUILDKIT=0
bash scripts/verify_local.sh
```

Runs the real separate-verifier image against the official solution, a second dataclass rewrite (`scripts/alt-hsm`), the bundled starter, and a hardcoded sample report. Required: 1, 1, 0, 0.

Mechanical subset of the implementation rubric (no LLM):

```bash
python3 scripts/check_implementation_rubric_mechanical.py
```

Harbor agent-install network preflight (the step that previously raised `NetworkConnectionError`):

```bash
bash scripts/preflight_agent_network.sh
```

### Standard agent trials (CI `/run`)

Three trials each, matching [docs/harbor-run-defaults.yml](docs/harbor-run-defaults.yml):

```bash
# Codex (gpt-5.6-sol, reasoning_effort=xhigh). Login first: `codex login`
harbor run -p tasks/scan-margin \
  --agent codex --model openai/gpt-5.6-sol \
  --env docker --yes -k 3 \
  --ae CODEX_FORCE_AUTH_JSON=1 --ak reasoning_effort=xhigh \
  -o results/run-codex

# Claude Code (claude-opus-5, reasoning_effort=max). Token: `claude setup-token`
harbor run -p tasks/scan-margin \
  --agent claude-code --model anthropic/claude-opus-5 \
  --env docker --yes -k 3 \
  --ae CLAUDE_FORCE_OAUTH=1 \
  --ae CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 \
  --ak reasoning_effort=max \
  -o results/run-claude
```

Or: `bash scripts/run_trials.sh run-codex` / `run-claude`.

The hiring bar: every completed trial must fail the verifier (reward `< 1`). Crashes, rate limits, container failures, and timeouts do not count as model failures.

### Adversarial trials (CI `/cheat`)

One trial each. The official hack prompt is appended (`--extra-instruction-path docs/hack-trial-prompt.md`). Every cheat trial must score reward `0`.

```bash
bash scripts/run_trials.sh cheat-codex
bash scripts/run_trials.sh cheat-claude
```

## Recorded results

See [EVALUATION.md](EVALUATION.md) for check logs, Harbor `result.json` pointers, trial tables, and failure analysis.
