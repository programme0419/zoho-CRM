#!/usr/bin/env bash
# Harbor commands matching current Terminal-Bench 3 CI defaults
# (.github/harbor-run-defaults.yml as of 2026-09-04).
#
# Standard /run: 3 trials each of
#   claude-code + anthropic/claude-opus-5 + reasoning_effort=max
#   codex       + openai/gpt-5.6-sol      + reasoning_effort=xhigh
# Adversarial /cheat: 1 trial each of the same two configs, with the
# official hack-trial prompt appended.
#
# Codex:  login first (`codex login`), then this script uses
#         CODEX_FORCE_AUTH_JSON=1.
# Claude: run `claude setup-token` and export CLAUDE_CODE_OAUTH_TOKEN.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"
TASK="${TASK:-tasks/scan-margin}"
OUT="${OUT:-$ROOT/results}"

run_standard() {
  local agent="$1" model="$2" effort="$3" extra_ae="$4" dest="$5"
  # shellcheck disable=SC2086
  harbor run -p "$TASK" \
    --agent "$agent" --model "$model" \
    --env docker --yes -k 3 -n 1 \
    --ak "reasoning_effort=${effort}" \
    $extra_ae \
    -o "$dest"
}

run_cheat() {
  local agent="$1" model="$2" effort="$3" extra_ae="$4" dest="$5"
  # shellcheck disable=SC2086
  harbor run -p "$TASK" \
    --agent "$agent" --model "$model" \
    --env docker --yes -k 1 -n 1 \
    --ak "reasoning_effort=${effort}" \
    --extra-instruction-path "$ROOT/docs/hack-trial-prompt.md" \
    $extra_ae \
    -o "$dest"
}

case "${1:-help}" in
  oracle)
    harbor run -p "$TASK" --agent oracle --env docker --yes -o "$OUT/oracle"
    ;;
  nop)
    harbor run -p "$TASK" --agent nop --env docker --yes -o "$OUT/nop"
    ;;
  run-codex)
    run_standard codex openai/gpt-5.6-sol xhigh "--ae CODEX_FORCE_AUTH_JSON=1" "$OUT/run-codex"
    ;;
  run-claude)
    : "${CLAUDE_CODE_OAUTH_TOKEN:?set CLAUDE_CODE_OAUTH_TOKEN from \`claude setup-token\`}"
    run_standard claude-code anthropic/claude-opus-5 max \
      "--ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN} --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000" \
      "$OUT/run-claude"
    ;;
  cheat-codex)
    run_cheat codex openai/gpt-5.6-sol xhigh "--ae CODEX_FORCE_AUTH_JSON=1" "$OUT/cheat-codex"
    ;;
  cheat-claude)
    : "${CLAUDE_CODE_OAUTH_TOKEN:?set CLAUDE_CODE_OAUTH_TOKEN from \`claude setup-token\`}"
    run_cheat claude-code anthropic/claude-opus-5 max \
      "--ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN} --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000" \
      "$OUT/cheat-claude"
    ;;
  *)
    echo "usage: $0 {oracle|nop|run-codex|run-claude|cheat-codex|cheat-claude}"
    exit 2
    ;;
esac
