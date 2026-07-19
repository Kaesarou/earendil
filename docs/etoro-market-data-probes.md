# eToro Market Data probes

This PR adds sidecar diagnostics only. The probes cannot place or close an
order and reject every broker configuration except `BROKER=etoro_demo`.
WebSocket and historical data are never exposed to Goblin's strategy,
position management, TP/SL logic, ranking, or execution pipeline.

## Official contract used by the probes

Checked on 2026-07-19:

- eToro's official example connects to `wss://ws.etoro.com/ws`, sends an
  `Authenticate` operation containing `userKey` and `apiKey`, and then sends a
  `Subscribe` operation.
- price topics use `instrument:<instrumentId>` and support an initial
  `snapshot` flag.
- instrument messages contain an outer message id and a JSON-encoded `content`
  object with `Ask`, `Bid`, `LastExecution`, `Date`, and `PriceRateID`.
- `PriceRateID` is documented as a unique rate identifier. It is not documented
  as a contiguous sequence, so the probe uses it for duplicate detection only;
  it does not invent sequence gaps.
- the official topic list documents instrument rates and a private transaction
  stream. It does not document a WebSocket candle topic.
- the REST candle contract supports `asc` and `desc`, intervals from
  `OneMinute` to `OneWeek`, and at most 1000 candles per request.

References:

- [WebSocket overview](https://api-portal.etoro.com/api-reference/websocket/overview)
- [WebSocket authentication](https://api-portal.etoro.com/api-reference/websocket/authentication)
- [WebSocket topics](https://api-portal.etoro.com/api-reference/websocket/topics)
- [WebSocket example](https://api-portal.etoro.com/api-reference/websocket/example-code)
- [REST candle history](https://api-portal.etoro.com/api-reference/market-data/get-instrument-candle-history)

The official pages currently do not specify subscription limits, connection
limits, an application heartbeat, ordering guarantees, replay, retention, or a
resume cursor. Those properties remain unknown until eToro documents them or
the probe produces repeatable observations. Transport ping/pong only proves
that the socket is reachable; it does not prove that prices are fresh.

## Sunday crypto protocol

The normal Goblin launcher is unchanged. The probe has its own Docker Compose
wrapper and reads its symbols from the existing `.env` file.

Required configuration for the crypto test:

```dotenv
BROKER=etoro_demo
ETORO_API_KEY=...
ETORO_USER_KEY=...
WATCHLIST=BTC,ETH,SOL
CRYPTO_SYMBOLS=BTC,ETH,SOL
MARKET_BENCHMARK_CRYPTO=Crypto10
```

## End-to-end test procedure

Fetch and select only the WebSocket study branch:

```bash
git fetch origin
git switch agent/etoro-market-data-study
git pull --ff-only origin agent/etoro-market-data-study
```

Update `.env` with the demo credentials and crypto configuration shown above.
Do not merge or switch to the portfolio-reconciliation branch for this test.

Stop any normal Goblin container before collecting data, otherwise its REST
polling would contaminate the request count:

```bash
docker compose down
```

An optional five-minute smoke run verifies authentication, subscription,
capture, and container wiring:

```bash
bash scripts/run_market_data_probe.sh compare 300
```

Then execute Window A and Window B below. Every invocation rebuilds the image
from the selected branch. Captures survive container removal through the
existing `./data:/app/data` volume.

After a run, find its unique output directory and inspect `summary.json` and
`events.jsonl` before starting the next window:

```bash
ls -1dt data/market-data-study/* | head -1
```

### Window A — quality comparison

Run WebSocket continuously while preserving Goblin's current REST shape: one
tradable batch and one benchmark batch every 10 seconds.

```bash
bash scripts/run_market_data_probe.sh compare
```

The default duration is 1800 seconds. A shorter smoke run can be requested as
the optional second argument, for example
`bash scripts/run_market_data_probe.sh compare 300`.

This window answers whether WebSocket observations are more frequent, fresher,
less repetitive, and closer to the high/low of subsequently closed REST M1
candles. It does not claim a REST saving because polling is deliberately kept
as the control.

### Window B — request reduction

Run WebSocket continuously and reduce both REST groups to one validation every
60 seconds:

```bash
bash scripts/run_market_data_probe.sh ws-primary
```

The default duration is 3600 seconds. The wrapper builds the current branch,
starts a one-off container with the repository `.env`, mounts `./data`, and
removes the container when the probe completes. It does not start `app.main`.

This is still a data-only sidecar. `ws-primary` describes the acquisition mode
inside the probe; it does not make WebSocket authoritative for Goblin.

The default forced disconnect occurs after two minutes. Successful
authentication, resubscription, silences, transport pongs, reconnects, and
connection failures are recorded. Two consecutive silent windows force a new
connection even if transport ping/pong succeeds.

## Request budget

Nominal market-rate calls, excluding startup instrument searches, the final
historical-candle control, retries, portfolio, and trading endpoints:

| Mode | Tradable batches/min | Benchmark batches/min | Total rates GET/min | Reduction |
|---|---:|---:|---:|---:|
| Current / comparison control | 6 | 6 | 12 | 0% |
| WS-primary validation | 1 | 1 | 2 | 83.3% |

With the default four instruments, each run also performs four logical search
operations at startup and four M1 candle requests at the end. The summary keeps
those categories separate. Request savings are therefore reported both for the
steady-state rates budget and as raw category totals.

## Captures

Each run receives a unique directory under
`data/market-data-study/<run-id>/`. Reusing a non-empty directory is rejected.

- `manifest.json`: immutable run intent, source commit, symbols, intervals, and
  explicit `orders_enabled: false`.
- `raw_websocket.jsonl`: broker authentication responses and stream envelopes.
- `raw_rest_rates.jsonl`: raw rates payloads, duration, status, and allow-listed
  diagnostic response headers.
- `raw_rest_candles.jsonl`: raw historical candle responses.
- `normalized_rates.jsonl`: common REST/WS rate representation with provenance.
- `normalized_candles.jsonl`: historical candles with an explicit
  `potentially_incomplete` flag.
- `events.jsonl`: connection, silence, reconnect, parsing, and request errors.
- `summary.json`: request budget, data age, duplicates, out-of-order timestamps,
  repeated prices, and OHLC comparison.

Credentials and outbound authentication payloads are never written.

## Decision criteria

Do not promote WebSocket into Goblin from a single successful connection. A
favorable technical result requires all of the following across repeated runs:

1. authentication and forced reconnection both recover without manual action;
2. silent data is detected even when transport ping/pong remains healthy;
3. no unexplained duplicate or out-of-order pattern remains;
4. WebSocket has materially more observations per closed minute than REST;
5. WebSocket has smaller missed-high and missed-low errors against delayed REST
   candles than the 10-second polling control;
6. data age remains bounded per instrument, including quiet periods;
7. the `ws-primary` window demonstrates the expected steady-state rate-request
   reduction without losing captures or accumulating parse errors.

Even after those criteria pass, the next step is shadow mode. Replacing the
runtime polling or using WebSocket for bot-managed stops requires a separate PR
with an explicit freshness state machine, deterministic REST fallback, gap
repair, and entry suspension while data quality is degraded.
