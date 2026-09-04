# Harbor agent-install network preflight

Date: 2026-09-04T17:34:00Z

Harbor Codex/Claude `install()` runs this inside the task container:

```
apt-get update && apt-get install -y curl bash nodejs npm ripgrep
```

Earlier `/run` and `/cheat` Codex jobs failed here (`NetworkConnectionError`, IPv4 timeout to `deb.debian.org`). That is infrastructure, not a model failure.

Re-run on this host against `python:3.13-slim-bookworm`: **PASS** (packages installed; `curl`, `node`, `npm`, `rg` present).

A logged-in retry of `scripts/run_trials.sh run-codex` / `cheat-codex` can now get past agent install. The trial still needs `~/.codex/auth.json` or `OPENAI_API_KEY`, and Claude trials still need `CLAUDE_CODE_OAUTH_TOKEN`.
