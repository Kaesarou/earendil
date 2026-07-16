# PR5-C — Fixed profiles and TP-aware calibration

## Purpose

PR5-C makes one event the center of Goblin V1:

> the effective TP is reached before the effective SL, after accounting for the profile, market context, timing and costs.

The PR deliberately removes the implicit US fixed/dynamic dual system. It does not implement the future attainable-target model.

## Replaced contracts

Removed rather than deprecated:

- US ATR-derived TP/SL;
- `dynamic_sl_tp_enabled`;
- `dynamic_min_score`;
- `missing_atr_fallback_fixed`;
- dynamic raw/floor/cap metadata;
- absolute movement-consumed thresholds;
- asset-only probability calibration;
- gross-only breakeven naming and behavior.

## Named fixed profiles

- `us_intraday_fixed_v1`: TP 1.20%, SL 0.70%, stale 60 minutes;
- `eu_trend_buy_v1`: TP 2.00%, SL 1.20%, stale 180 minutes;
- `eu_intraday_fixed_v1`: TP 1.00%, SL 0.70%, stale 75 minutes;
- `crypto_intraday_fixed_v1`: TP 3.00%, SL 1.50%, stale 60 minutes.

Pending confirmations may replace the baseline SL with a structural invalidation distance. The TP and probability calibration still refer to the baseline named profile.

## Entry freshness

```text
movement_consumed_to_tp_ratio
= max(directional session move, 0) / effective TP
```

This ratio is converted continuously to `entry_freshness_score`.

Freshness has two roles only:

1. one component of TP feasibility;
2. a gate on positive relative-strength compensation.

It is not separately added to context and probability multiple times.

## Market context v2

```text
market background
= benchmark session
+ benchmark momentum
+ breadth
+ sector
```

Relative strength is then applied:

```text
relative adjustment
= raw relative adjustment × freshness factor
```

For a hostile background, relative strength may compensate the complete malus and add at most two extra points. For a favorable background, it adds at most four points. Negative relative strength remains a bounded malus. Total context is bounded to ±15.

No context value can produce `SKIP`, invalidate a pending setup or force a retest.

## TP feasibility v3

Components:

- TP/ATR: 30%;
- TP/momentum: 25%;
- costs/TP: 30%;
- entry freshness: 15%.

The score contributes from -15 to +15. Costs greater than or equal to TP remain the sole feasibility hard rejection.

## Probability heuristic v4

The model consumes direct components once each. It no longer combines the aggregate feasibility score with the same ATR, momentum, cost and freshness inputs again.

Context and READY MTF are explicit probability inputs.

Calibration keys are profile and side, not asset class alone. EV remains a ranking value inside score buckets and never rejects a candidate.

## Session horizon

For a finite session:

```text
available minutes >= stale horizon + force-close buffer
```

The constraint applies before creating a new candidate and before confirming a pending candidate. Rejections use `insufficient_session_time_for_trade_horizon` and retain required/available minutes plus profile key.

## Managed protection

Net breakeven locks:

```text
estimated total cost percent + configured net buffer
```

Trailing behavior retains the existing net-lock test. Every managed-stop change emits `managed_stop_updated` and the current position is immediately persisted.

## Analysis schema v8

Standalone `entry_decision` records expose:

- profile and effective SL/TP;
- consumed/TP ratio and freshness;
- final context components;
- READY MTF contribution;
- probability calibration profile;
- route and selection outcome.

The summary counts only selected candidates in the RiskManager stage and reports horizon rejections and managed-stop updates.

## Deliberate non-goals

- attainable dynamic TP V2;
- MTF weight changes;
- EV hard gate;
- daily-loss or drawdown limits during demo collection;
- crypto deletion;
- live-readiness claims.
