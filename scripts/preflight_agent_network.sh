#!/usr/bin/env bash
# Harbor's Codex/Claude installers run this exact apt-get inside the task
# container. Previous /run and /cheat jobs died here (NetworkConnectionError).
# A pass means a retry of those trials can get past agent install.
set -euo pipefail
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"
IMG="${IMG:-python:3.13-slim-bookworm}"
echo "Preflight: apt-get update && apt-get install -y curl bash nodejs npm ripgrep"
docker run --rm -e DEBIAN_FRONTEND=noninteractive "$IMG" \
  bash -lc 'apt-get update && apt-get install -y curl bash nodejs npm ripgrep && command -v curl && command -v node && command -v npm && command -v rg'
echo "Agent-install apt-get preflight passed"
