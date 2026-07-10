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
- daily summaries and reproducible run manifests
- deterministic market replay and baseline comparison

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

Normal mode keeps raw market data for replay while avoiding one JSONL line for every HOLD decision.

Main files:

```text
data/logs/trades.jsonl
data/logs/errors.jsonl
data/logs/market.jsonl.gz
data/logs/candles.jsonl.gz
data/logs/daily_summary.json
data/logs/run_manifest.json
```

Each run also archives its reproducibility files under:

```text
data/logs/runs/<run_id>/run_manifest.json
data/logs/runs/<run_id>/daily_summary.json
```

The manifest contains the Git commit, the complete non-secret settings snapshot, the strategy profile, the instrument configuration, the watchlist and the paths of the replay sources.

Every JSONL record contains a `run_id`, stream name and contiguous sequence. Replay stops with an integrity error if market records are missing or out of order.

## Replay a run

Run the replay from the archived manifest:

```bash
python -m app.replay.cli data/logs/runs/<run_id>/run_manifest.json
```

The command:

- validates the market, candle and trade streams;
- rebuilds candles and strategy decisions from raw market snapshots;
- rebuilds candidates and the pre-economics min-score/top-n selection;
- compares simulated candidates with the real run;
- lists additional winning and losing counterfactual candidates;
- writes `replay_report.json` in the run archive and updates the latest report.

The counterfactual TP/SL outcome is a screening tool. It uses `snapshot.last` and static risk-profile percentages. It does not yet reproduce broker slippage, fees, cooldown, account-equity limits or position overlap.

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
│   ├── replay/
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
