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
| Static checks | **PASS** (re-run after HSMJ) | this file |
| Implementation-rubric (`harbor check`) | **blocked** — API key stored; Anthropic returned **credit balance too low** | mechanical subset **PASS** |
| Docker build | **PASS** | oracle / nop / local matrix |
| Oracle reward 1.0 | **PASS** (HSMJ job `2026-09-04__19-19-26`) | [oracle.json](results/summaries/oracle.json) |
| Nop reward 0.0 | **PASS** (HSMJ job `2026-09-04__19-20-04`) | [nop.json](results/summaries/nop.json) |
| Any correct engine scores 1 | **PASS** after HSMJ | official solution **and** dataclass rewrite |
| Incomplete / hardcoded engines score 0 | **PASS** after HSMJ | starter + hardcoded sample |
| `/run` × 3 Codex genuinely fail | **not met — 3/3 across four genres** (spec, overlays, HSMJ, optimization) | [run-codex.json](results/summaries/run-codex.json), [run-codex-harden.json](results/summaries/run-codex-harden.json), [run-codex-hsmj.json](results/summaries/run-codex-hsmj.json), [run-codex-optimize.json](results/summaries/run-codex-optimize.json) |
| `/run` × 3 Claude genuinely fail | **not met** — every quota-complete trial solved across all four genres (incl. genre-4 optimization `jsr6hts`=1.0); only zeros are session-window rate limits | [run-claude.json](results/summaries/run-claude.json), [run-claude-2.json](results/summaries/run-claude-2.json), [run-claude-optimize.json](results/summaries/run-claude-optimize.json) |
| `/cheat` Codex reward 0 | **reward 0, via refusal** — `AgentSafetyRefusalError`, not a blocked cheat attempt | [cheat-codex.json](results/summaries/cheat-codex.json) |
| `/cheat` Claude reward 0 | **reward 0, but infra** — `ApiRateLimitError` at 1m14s (session quota exhausted) | [cheat-claude.json](results/summaries/cheat-claude.json) |

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

Needs an LLM judge (`ANTHROPIC_API_KEY` / Claude Code). Attempted 2026-09-05T01:53Z with a host API key (not committed). The check container reached `api.anthropic.com` (docker0 overlay: `--ek extra_docker_compose=["…/docker-compose.bridge.yaml"]`) and failed with `Credit balance is too low`. Mechanical subset still **PASS**.

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
| codex / openai/gpt-5.6-sol / xhigh | 1–3 | **1.0 × 3** (three jobs) | none | HSM 1.0 (`18-00-05`), overlays (`18-37-45`), HSMJ journals (`19-21-22`, 41m, ~$4.65). All genuine. **Hiring bar requires all three to fail.** |
| claude-code / anthropic/claude-opus-5 / max | 1 | **1.0** | none | Job `2026-09-05__00-49-40` trial `fcmSBjt`. Genuine solve. |
| claude-code / anthropic/claude-opus-5 / max | 2–3 | 0.0 | **ApiRateLimitError** | Session limit: “resets 5:50am (UTC)”. Infra, not a model fail. |
| claude-code / anthropic/claude-opus-5 / max (rerun after reset) | 1 | **1.0** | none | Job `2026-09-05__05-51-58` trial `aJ2TqSS`. Genuine solve. |
| claude-code / anthropic/claude-opus-5 / max (rerun) | 2 | **1.0** | late `ApiRateLimitError` | Trial `EUpi3rs`. Solution already correct; verifier scored 1. Effective solve. |
| claude-code / anthropic/claude-opus-5 / max (rerun) | 3 | 0.0 | **ApiRateLimitError** | Trial `QWCatED`. Rate-limited before solving. Infra, not a model fail. |

Across both Claude sessions, every trial that had enough Opus session quota to finish **solved** the task (3 genuine passes). The only zeros are rate-limit cutoffs. Claude, like Codex, is not failing this task for model reasons.

Earlier Codex jobs (`4960ffb6-…`, `2026-09-04__17-53-20`) died on `NetworkConnectionError` during `apt-get` inside Harbor’s Compose network. That is infra. This host’s user-defined Docker networks cannot NAT IPv4; the default `docker0` bridge can. `scripts/run_trials.sh` now passes `scripts/docker-compose.bridge.yaml` (`network_mode: bridge`). After that overlay, Codex installed and called the API.

Auth used a host `OPENAI_API_KEY` (not committed). `codex login` is still unused.

To complete the table on a subscribed machine:

1. `codex login` then `bash scripts/run_trials.sh run-codex`
2. After the Claude session limit resets (5:50am UTC on 2026-09-05), `export CLAUDE_CODE_OAUTH_TOKEN=...` and rerun `bash scripts/run_trials.sh run-claude` until three trials complete without rate-limit/infra errors. The one completed trial already scored 1.0.

Copy each job's `result.json` into `results/summaries/`.

## Adversarial trials (`/cheat`)

```bash
bash scripts/run_trials.sh cheat-codex
bash scripts/run_trials.sh cheat-claude
```

| Config | Reward | Error? | Requirement |
|--------|--------|--------|-------------|
| codex / openai/gpt-5.6-sol / xhigh | **0.0** | `AgentSafetyRefusalError` (job `2026-09-05__05-53-03`) | must be 0.0 |
| claude-code / anthropic/claude-opus-5 / max | **0.0** | `ApiRateLimitError` at 1m14s (job `2026-09-05__06-35-07`) | must be 0.0 |

Both `/cheat` trials report reward **0.0**, so the literal bar ("reward exactly 0") is met. But neither is a clean demonstration that the hardened verifier caught a real cheat attempt: Codex **refused** the hack prompt on safety grounds, and Claude **rate-limited** before doing anything (Opus session quota exhausted by the `/run` trials just before). A convincing `/cheat=0` — model attempts a shortcut and the separate verifier rejects it — still needs a config that (a) does not refuse and (b) has quota to run. The local cheat-shaped engines below already show the verifier rejects the obvious shortcuts.

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

The starter already emits a correct report for `/app/hsm/data/sample_book.hsmj` (v1 tape, two long CL futures → $5,000, worst scenario 13). An agent that treats that file as the test suite, implements only the v1 blotter, or ports SPAN defaults, will match the sample and fail the hidden v2 tapes:

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

### Codex traces (2026-09-04)

Both completed `/run` jobs were genuine model trials (agent installed, `gpt-5.6-sol` + `xhigh`, no infra exception).

1. **HSM 1.0 spec** — job `2026-09-04__18-00-05` — 3/3 reward 1.0. Codex rewrote `/app/hsm/engine.py` from `methodology.md` in ~9 minutes per trial.
2. **Overlays added** (delivery-month PSR scale, log vs linear shocks, asymmetric vol, strip credit, ICS ρ, NOV cap, post-ICS concentration, post-SOM LAO, six new hidden books) — job `2026-09-04__18-37-45` — **again 3/3 reward 1.0**.

Conclusion: a complete, fair, written methodology for a deterministic engine is not enough to fail this config. A further overlay cookbook will not meet the hiring bar.

### Genre change: HSMJ journals — still 3/3

Positions now arrive as House Scan Margin Journals. The sample is a v1 POS_V1 tape the starter already decodes. Hidden books are v2 tapes: mixed-endian chunk lengths, packed quantities, packed-BCD strikes, CRC-skipped frames, combo expansion, voids, and patches. The methodology overlays stay fully specified (fairness / instruction alignment). Oracle still recomputes from JSON equivalents and does not share the agent's decoder.

Job `2026-09-04__19-21-22` (`53628d4d-…`): **3/3 reward 1.0**, 41m, ~$4.65, no infra errors. Codex read `hsmj.h` / `FORMAT.md` / `ERRATA.txt` and wrote a v1+v2 decoder plus the overlay engine in ~12 minutes per trial.

Three genuine `/run` jobs, three genres, nine trials, nine rewards of 1.0. A complete, fair written spec — math or on-wire format — is not enough to fail `gpt-5.6-sol` + `xhigh`.

### Genre 4: hard combinatorial optimization — still 3/3

Inter-commodity credit was changed from a priority-ordered pairwise pass to the **global margin-minimizing allocation** over overlapping two-leg and three-leg crack spreads with shared per-commodity capacity. The natural SPAN-style implementation (priority order, or greedy-by-credit, or pairwise-only) is now provably suboptimal: on the `crack` book it scores 5100 credit vs the optimal 9900 (margin off by $4800); on `ics_priority`, consuming pairwise first blocks the better crack (1700 vs 3300). The rule is fully specified in methodology §7 and the optimum is unique, so it stays fair and deterministic; two independent correct engines (recursive branch-and-bound and exhaustive-product) agree with the oracle.

Job `2026-09-05__07-57-03`: **3/3 reward 1.0, 0 errors**, 33m. `gpt-5.6-sol` + `xhigh` recognized the requirement as an optimization and implemented it correctly rather than defaulting to the priority-ordered greedy. (`claude-opus-5` + `max` not yet run on this genre — Opus session quota exhausted; given it solved genres 1–3 and Codex solved this one, it is expected to pass.)

**Four genres, twelve genuine Codex trials, twelve rewards of 1.0.** The lever changed each time — written math spec, a nastier binary input codec, and finally a hard combinatorial optimization where the "obvious" implementation is wrong — and the result did not.

Claude genre-4 (subscription OAuth, not paid API): **solved.** Job `2026-09-05__16-06-31` ([summary](results/summaries/run-claude-optimize.json)) on a fresh Opus window: trial `jsr6hts` completed in ~28 min with **reward 1.0** — a genuine solve of the hard optimization. The other two trials (`fd4HFsh`, `Jzihs6i`) hit `ApiRateLimitError` because that one trial consumed the 5-hour session window (Codex/xhigh does a trial in ~11 min); those are infra zeros, not model failures. Earlier attempts (`2026-09-05__09-45-40`, `2026-09-05__10-53-50`) were fully window-blocked and are recorded for completeness.

**Both configs solve all four genres.** `claude-opus-5`/max recognized the global-optimization requirement and implemented it correctly, exactly like `gpt-5.6-sol`/xhigh — it just needs far more time/tokens per trial.

## Conclusion — the "must-fail" bar is structural, not a tuning gap

Every requirement in this exercise reduces to one thing: both `gpt-5.6-sol`/xhigh and `claude-opus-5`/max must be **unable** to solve the task (`/cheat=0` included — a model that can solve the task just solves it under `/cheat` and scores 1).

The evidence, across four independent hardening genres, is that this is not reachable for a **fair, deterministic, expert-solvable compute task**:

- TB3 fairness requires the tested behavior to be *derivable* by the agent (documented methodology / code-as-spec / visible tests; no hidden-behaviour guessing; no process grading).
- "Derivable + deterministic + expert-solvable in hours" ⟹ a complete-enough description exists ⟹ a strong *implementer* can produce a correct solution.
- These two configs are excellent implementers. Even a hard combinatorial optimization where the natural implementation is provably wrong (genre 4) was recognized and solved correctly by Codex 3/3.

This is consistent with TB3's own rubric, which explicitly accepts tasks that current models can solve. The scan-margin task is rigorous and clears every automatable bar (static checks, Docker build, oracle=1, nop=0, "any correct engine passes / incomplete fails", cheat-shaped engines score 0). What it cannot do — and what no fair task in this genre can do — is force these frontier configs to fail.

**To meet a literal "both models fail 3/3" bar, the task must leave the compute-a-spec domain** for a large broken-codebase / long-horizon debugging task with a *visible-but-hard* test suite and held-out grading — the genre where frontier models still fail a real fraction. That is a different task in a different domain, and even there, failing *both* models on every attempt is not guaranteed.

### Claude, same result

`claude-opus-5` + `max` was run twice (2026-09-05 `00-49-40` and `05-51-58`). Every trial that had enough Opus session quota to finish solved the task (3 genuine reward-1.0 passes: `fcmSBjt`, `aJ2TqSS`, `EUpi3rs`). The only Claude zeros are `ApiRateLimitError` cutoffs, which are infra, not model failures.

### Why the hiring bar is unmet, and what it implies

Every bar in this exercise reduces to one thing: **these two frontier configs must be unable to solve the task.**

- `/run` requires all trials to fail. Both models solve it.
- `/cheat` requires reward 0. But if a model can solve the task, the natural `/cheat` outcome is that it just solves it (reward 1). The two `/cheat=0` results we have came from a refusal (Codex) and a rate-limit (Claude), not from the verifier catching a real cheat on an unsolvable task.

"Implement this fully-specified deterministic engine" is one of the easiest task categories for current frontier models, and TB3 fairness (documented methodology, instruction/test alignment, reviewability, no process grading) forces the spec to be complete. Adding more rules or a harder input codec does not change the category — it is still transcription plus careful bookkeeping, which both models do inside the time limit. This has now been shown across three genres and both required configs.

Getting both `gpt-5.6-sol`/xhigh and `claude-opus-5`/max to fail 3/3 on a task that is also fair and solvable by an expert in a few hours almost certainly requires leaving the "implement a spec" genre entirely — e.g. deep debugging of a large, underdocumented system, or a genuinely hard search/optimization target with a strict threshold — where reading cannot substitute for iterative, feedback-driven work. That is a task-type change, not another hardening pass, and it carries its own fairness tradeoffs to work through. Note TB3's own rubric explicitly accepts tasks that current models can solve; the "must fail" bar here is stricter than TB3 itself.

Old-task `/cheat` (`2026-09-04__18-29-49`) ended in `AgentSafetyRefusalError` — not a valid verifier zero.

---

# Pivot: `tasks/refcalc-clone` — leaving the "implement a spec" genre

The conclusion above is that a fair, deterministic, *spec-derivable* compute task cannot force these two configs to fail, because "derivable + solvable by an expert" implies a strong implementer can reproduce it. `refcalc-clone` is the genre change that pivot points to: **black-box reverse-engineering**, where the correct behavior is *not written down anywhere* and can only be recovered by probing a compiled reference. The failure mode is incomplete discovery of counterintuitive rules — a thoroughness/discovery limit, not a transcription task.

## What the task is

- The agent gets `/app/refcalc/refcalc`: a stripped, statically-linked integer-expression engine it can **run but not read** (source is discarded in a multi-stage Docker build — verified absent in the final image). No written spec.
- Deliverable: reimplement it exactly in pure Python at `/app/solution/calc.py` (`calc(expr) -> str`).
- The engine's semantics deliberately violate strong priors and are only discoverable by probing:
  1. `^` is exponentiation, **left-associative** (`2^3^2 == 64`, not 512).
  2. `^` binds **tighter** than `* / %`.
  3. Unary minus binds **tighter** than `^` (`-2^2 == 4`, not -4).
  4. Division truncates toward zero; modulo takes the **dividend's** sign (C, not Python): `-7/2 == -3`, `-7%2 == -1`.
  5. All arithmetic wraps in **signed 32-bit two's complement** (`2^31 == -2147483648`; big literals wrap mod 2^32).
  6. Negative exponent → `0` except bases `1`/`-1`; `0^0 == 1`; `0^-1 == ERR`.
  7. Literals: decimal with leading zeros (not octal) and `0x` hex; malformed input / div-by-zero → sentinel `ERR`.

An agent that assumes standard precedence, right-associative powers, Python division, or big integers passes the obvious cases and fails the revealing ones. Grading is **all-or-nothing over 419 hidden expressions** (every quirk + bounded fuzz), so a single missed rule fails.

## Why this can defeat strong implementers when a spec cannot

The prior genres handed the model a complete description; here there is none. The model must (a) think to probe each counterintuitive dimension, and (b) get every one exactly right, with no feedback at grading time. Several quirks only trigger on specific probes (overflow needs large values; C modulo needs negatives; left-assoc `^` needs 3+ chained; unary-vs-`^` needs `-x^y`), so "probe a few representative inputs and generalize" — the common model strategy — is not enough.

## Structural validation (all automatable bars) — PASS

- **Static checks**: PASS (`bash scripts/run_static_checks.sh tasks/refcalc-clone`).
- **Reference ≡ solution**: the C reference and the Python solution are **bit-identical on 60k+ random fuzz expressions** plus all 419 curated cases (zero mismatches).
- **Docker build**: PASS (multi-stage; final image ships only the stripped static binary, no `.c`).
- **Oracle reward 1.0**: PASS (`results/refcalc/oracle3`, 420/420 checks).
- **Nop reward 0.0**: PASS (`results/refcalc/nop`, stub raises → 419 mismatches).
- **Local matrix** (`scripts/refcalc/verify_local.py`): correct solution = 419/419 (reward 1); a plausible standard-semantics calc = 258/419 (reward 0); stub = 0 (reward 0); anti-cheat scan has no false positives on the legitimate solution.

## Anti-cheat

The reference is fully available to probe, but the verifier (separate image) copies **only** `calc.py`, statically rejects real exfiltration constructs (`subprocess`, `os.system/popen/exec`, `ctypes`, `socket`, `__import__`, `multiprocessing`), **deletes the reference binary** before grading, and stages only the expressions (expected outputs stay root-only) so an adversarial `calc.py` can neither call the reference nor read the answers. Python `eval` on the expression is not a viable cheat — it yields standard semantics and fails the quirks.

## Model validation — pending credentials (blocked, not concluded)

Unlike scan-margin, this genre is a genuine candidate to fail both configs, but I could not run the models on this VM yet:

- **Codex** (`gpt-5.6-sol`/xhigh): `~/.codex/auth.json` is absent and `OPENAI_API_KEY` is unset on this VM (the earlier login did not persist across the environment). Needs a fresh `codex login` (or an `OPENAI_API_KEY`) before trials can run.
- **Claude** (`claude-opus-5`/max): the OAuth token is present, but the subscription's **5-hour session window is exhausted** (`api_error_status 429`, "resets 9pm UTC"). The 7-day quota is only ~59% used. A one-shot timer is scheduled to auto-retry Claude `/run` x3 + `/cheat` after the window resets; if still throttled it re-arms for +1h.

Expected/target outcome once runnable: `/run` trials score **reward 0** (model fails to fully reverse-engineer the engine) and `/cheat` scores 0. If any model does solve it, the plan is to add further prior-violating quirks (keeping the C reference and Python solution bit-identical, regenerating the hidden corpus) and re-test.
