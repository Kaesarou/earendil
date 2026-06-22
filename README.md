# Eärendil

**Eärendil** is a deterministic intraday trading bot skeleton.

The goal is not to let an AI place trades. The trading engine stays deterministic, auditable and backtestable. AI can later be added as an offline analysis tool for logs and strategy improvement.

## Current stage

This first skeleton contains:

- Docker + Docker Compose setup
- Python project structure
- environment-based configuration
- broker abstraction
- eToro client placeholder
- market data service
- breakout strategy skeleton
- risk manager
- paper execution engine
- trade journal
- main bot loop

By default, the bot runs in `paper` mode and does not place real orders.

## Quick start

```bash
cp .env.example .env
```

Fill your demo API keys in `.env`, then run:

```bash
docker compose up --build
```

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
│   ├── backtesting/
│   ├── ai/
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

- Real trading is disabled by default.
- The bot should start with demo or paper trading only.
- Risk rules are centralized in `app/risk/risk_manager.py`.
- Broker-specific code stays isolated in `app/brokers/`.
- Strategies must be testable without broker access.

## Next steps

1. Validate eToro authentication.
2. Fetch a real market price.
3. Store market snapshots.
4. Implement first breakout strategy.
5. Run paper trading.
6. Add backtests.
7. Only then consider demo/prod execution.
