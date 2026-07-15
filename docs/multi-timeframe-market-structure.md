# Multi-timeframe market structure and scoring

This document describes Goblin's deterministic multi-timeframe layer and its PR5-B contribution to live candidate scoring.

## Fixed timeframe invariant

M1 is the canonical base timeframe. Higher timeframes are fixed constants:

```text
M1  = 60 seconds
M5  = 300 seconds
M15 = 900 seconds
M30 = 1800 seconds
H1  = 3600 seconds
```

`CANDLE_TIMEFRAME_SECONDS` does not exist. `POLL_INTERVAL_SECONDS` controls broker sampling frequency, not candle duration.

## Aggregation

Higher-timeframe bars are built only from closed contiguous M1 bars:

```text
5 complete M1  -> M5
15 complete M1 -> M15
30 complete M1 -> M30
60 complete M1 -> H1
```

Each `TimeframeBar` records:

- OHLC candle;
- timeframe and session key;
- actual and expected source-bar counts;
- missing source bars;
- completeness status.

Statuses are:

- `complete` — all expected M1 bars exist;
- `incomplete` — one or more M1 bars are missing or non-contiguous;
- `partial` — session/runtime ended before the bucket closed.

Incomplete and partial bars are journalled but never used for complete feature calculations. Goblin never fabricates a missing candle.

## Session anchoring

Finite equity sessions are anchored to their configured opening time. A US session opening at 15:30 produces:

```text
M30: 15:30-16:00, 16:00-16:30, ...
H1:  15:30-16:30, 16:30-17:30, ...
```

A bar never crosses two session keys. Open higher-timeframe buckets are flushed as partial on session transition or shutdown.

## Timeframe maturity

Each timeframe has one of three maturity states:

- `UNAVAILABLE` — too little closed history;
- `PROVISIONAL` — short-history diagnostics are available;
- `READY` — the timeframe has enough complete bars for its configured feature set.

The model does not fabricate full ATR, range or compression features from insufficient history.

## Features

A mature `TimeframeFeatures` value may contain:

### Trend and movement

- fast and slow EMA;
- close versus EMA;
- one-bar and sample returns;
- velocity and acceleration;
- descriptive direction: `up`, `down`, `mixed`, `unknown`.

### Volatility and range

- ATR percent;
- rolling high, low and range;
- position inside the range;
- distance to range boundaries;
- previous-bar high and low.

### Candle structure

- body percentage;
- upper and lower wick percentages;
- close position inside the candle.

### Compression and pullback

- current true range versus historical median;
- pullback from recent high;
- rebound from recent low.

Feature windows are code-versioned per asset class. Timeframe durations are not profile parameters.

## Opening ranges

Finite sessions expose 15-minute and 30-minute opening ranges by default. Each range records:

- `warming_up`, `ready`, `incomplete` or `not_applicable`;
- high, low and range percentage;
- current position and boundary distances;
- breakout/breakdown percentages;
- actual and expected M1 counts.

A missing M1 makes the opening range incomplete.

## Candidate context

Every candidate may carry an immutable `MultiTimeframeContext` containing:

- model version `multi_timeframe_features_v2`;
- exact `as_of` timestamp;
- feature and maturity maps by timeframe;
- opening-range snapshot;
- aligned/opposed timeframe lists;
- `ready_alignment`;
- `alignment_including_provisional`.

## PR5-B live score contribution

MTF is no longer purely diagnostic. Only `READY` directions contribute to the live candidate score:

| Timeframe | Aligned | Opposed |
|---|---:|---:|
| M5 `READY` | +4 | -4 |
| M15 `READY` | +6 | -6 |
| M30 `READY` | +2 | -2 |
| H1 | 0 | 0 |
| `PROVISIONAL` | 0 | 0 |

The total contribution is bounded to `[-10, +10]`.

### Why H1 remains neutral

H1 is rarely mature during an intraday session without historical warm-start data. Giving it live authority would make candidate scoring depend heavily on time of day and process uptime.

### Why provisional data remains neutral

A provisional direction is retained for analysis but has insufficient history to modify live risk-taking. It is neither a bonus nor a penalty.

### No MTF veto

MTF can increase or reduce the score. It cannot:

- directly return `SKIP`;
- invalidate a pending entry;
- bypass economics or risk;
- authorize an order below the selection threshold.

## Pending entries

When a retest confirms, the candidate is rebuilt using:

- current accepted snapshot;
- current closed M1 candle;
- current market context;
- current multi-timeframe context;
- current economics and feasibility;
- original candidate and pending lineage.

A satisfied confirmation is marked explicitly and cannot request the same retest again.

## No-lookahead guarantee

A feature may use only bars satisfying:

```text
bar.closed_at <= candidate.candle.closed_at
```

Open or future bars cannot alter a context rebuilt for a historical `as_of` timestamp. Dedicated tests enforce the invariant.

## Journals and analysis

The candle stream may include:

- `candle_closed`;
- `candle_gap_detected`;
- `timeframe_bar_closed`;
- `timeframe_bar_incomplete`;
- `timeframe_bar_partial`.

Every evaluated candidate's standalone `entry_decision` includes:

- complete MTF context;
- MTF feature model version;
- MTF score model version;
- total MTF score;
- per-timeframe score components;
- route and selection outcome.

The daily schema-v7 summary reports maturity, alignment and score-contribution distributions.

## Current limitations

- No broker historical-candle warm start is performed.
- A restarted process must rebuild MTF history.
- All higher timeframes derive from the same sampled M1 source; they are not independent market feeds.
- Volume remains unavailable when broker snapshots do not provide it.
- MTF weights are initial demo calibration values and must be adjusted from subsequent labelled runs.
- No profitability claim follows from MTF scoring.
