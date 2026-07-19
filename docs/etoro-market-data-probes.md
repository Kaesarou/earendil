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

Install the project and provide demo credentials through `.env`:

```bash
python -m pip install -e ".[dev,market-data-probe]"
```

Required configuration:

```dotenv
BROKER=etoro_demo
ETORO_API_KEY=...
ETORO_USER_KEY=...
```

### Window A — quality comparison

Run WebSocket continuously while preserving Goblin's current REST shape: one
tradable batch and one benchmark batch every 10 seconds.

```bash
python -m scripts.run_etoro_market_data_probe \
  --mode compare \
  --symbols BTC,ETH,SOL \
  --benchmark Crypto10 \
  --duration-seconds 1800
```

This window answers whether WebSocket observations are more frequent, fresher,
less repetitive, and closer to the high/low of subsequently closed REST M1
candles. It does not claim a REST saving because polling is deliberately kept
as the control.

### Window B — request reduction

Run WebSocket continuously and reduce both REST groups to one validation every
60 seconds:

```bash
python -m scripts.run_etoro_market_data_probe \
  --mode ws-primary \
  --symbols BTC,ETH,SOL \
  --benchmark Crypto10 \
  --duration-seconds 3600
```

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
