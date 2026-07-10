# Eärendil

**Eärendil** is a deterministic intraday trading bot skeleton.

The goal is not to let an AI place trades. The trading engine stays deterministic, auditable and backtestable. AI can later be added as an offline analysis tool for logs and strategy improvement.

## Current stage

The project currently contains:

- Docker + Docker Compose setup
- environment-based configuration
- broker abstraction and eToro integration
- market snapshots and candle construction
- deterministic trend strategy
- candidate ranking and economic filters
- centralized risk management
- paper execution engine
- structured trade, error, market and candle journals
- daily summaries and per-run configuration manifests

By default, the bot runs in `paper` mode and does not place real orders.

## Quick start

```bash
cp .env.example .env
```

Fill your demo API keys in `.env`, then run:

```bash
docker compose up --build
```

## Journals and run analysis

Normal mode keeps enough information for post-session strategic analysis while avoiding one JSONL line for every HOLD decision.

Main files:

```text
data/logs/trades.jsonl
data/logs/errors.jsonl
data/logs/market.jsonl.gz
data/logs/candles.jsonl.gz
data/logs/daily_summary.json
data/logs/run_manifest.json
```

Each run also archives its context files under:

```text
data/logs/runs/<run_id>/run_manifest.json
data/logs/runs/<run_id>/daily_summary.json
```

The manifest contains the Git commit when available, a source fingerprint, the complete non-secret settings snapshot, the strategy profile, the instrument configuration and the watchlist.

Every JSONL record contains a `run_id`, stream name and sequence number. This makes it possible to isolate one run inside append-only files and to spot missing records during analysis.

For a complete post-session analysis, keep or send together:

- the archived `run_manifest.json` and `daily_summary.json` for the run;
- `trades.jsonl` and `errors.jsonl`;
- `market.jsonl.gz` and `candles.jsonl.gz`;
- `debug_decisions.jsonl.gz` only when the run used debug/full detail.

The raw market and candle streams remain the source material for manual analysis and counterfactual simulations outside the bot. Earendil does not run those simulations as part of this logging US.

## Project structure

```text
earendil/
├── app/
│   ├── main.py
│   ├── config/
│   ├── brokers/
│   ├── market/
│   ├── strategies/
│   ├── risk/
│   ├── execution/
│   ├── journal/
│   └── utils/
├── tests/
├── scripts/
├── data/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

## Safety principles

- The bot should start with demo or paper trading only.
- Risk rules are centralized in `app/risk/risk_manager.py`.
- Broker-specific code stays isolated in `app/brokers/`.
- Strategies must be testable without broker access.
- Secrets must never be written into manifests or journals.
