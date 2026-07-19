#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
if [[ "$MODE" != "compare" && "$MODE" != "ws-primary" ]]; then
  printf 'Usage: %s <compare|ws-primary> [duration-seconds]\n' "$0" >&2
  exit 2
fi

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

PROBE_ARGS=(--mode "$MODE")
if [[ -n "${2:-}" ]]; then
  PROBE_ARGS+=(--duration-seconds "$2")
fi

printf 'Building Goblin market-data probe | GIT_COMMIT=%s | mode=%s\n' \
  "$GIT_COMMIT" "$MODE"
docker compose build goblin

exec docker compose run --rm --no-deps goblin \
  python -m scripts.run_etoro_market_data_probe "${PROBE_ARGS[@]}"
