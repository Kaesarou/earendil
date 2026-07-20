# Market Data V2 — WebSocket runtime

Market Data V2 replaces the ten-second eToro rates polling loop with an
event-driven transport while preserving the PR5-D decision model.

## Runtime sources

- eToro WebSocket is the primary source in `auto` and `websocket` modes.
- REST rates are fetched every 60 seconds for diagnostics only.
- A grouped REST fallback is requested when an active symbol is silent longer
  than the configured threshold.
- Paper mode and explicit `polling` mode use the same event runtime through a
  polling feed; the strategy no longer owns transport concerns.

## Safety rules

- deduplicate by connection plus `message_id`, never by `price_rate_id`;
- reject events older than the last accepted source timestamp for the symbol;
- validate quotes before advancing the accepted timestamp watermark;
- block new entries while a symbol is stale, in REST fallback, recovering, or
  blocked;
- block entries produced from an M1 candle that used fallback data;
- keep REST control snapshots diagnostic when WebSocket is healthy;
- bound the transport queue and fail visibly on overflow;
- coordinate candidates by closed M1 minute before applying cross-symbol
  ranking.

## Deliberately unchanged

- PR5-D scores, thresholds, profiles, top-N and risk constraints;
- `LastExecution` remains the strategy and candle price;
- portfolio reconciliation cadence and request semantics;
- historical candle warm-up and gap repair;
- broker-side protective-stop policy.

Follow-up work is tracked in issues #28 through #32.
