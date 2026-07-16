#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${GIT_COMMIT:-}" ]]; then
  GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"
fi
if [[ -z "${GIT_COMMIT:-}" ]]; then
  GIT_COMMIT=unknown
fi
export GIT_COMMIT

printf 'Starting Goblin! with GIT_COMMIT=%s\n' "$GIT_COMMIT"
exec docker compose up --build
