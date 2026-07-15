# PR5-B — Continuous context, MTF scoring and EU trend BUY

## Goal

PR5-B replaces binary context decisions and saturated TP penalties with explicit score contributions. It also fixes the pending lifecycle and introduces a dedicated longer-horizon EU BUY profile.

This is a deliberate contract replacement. No legacy aliases, micro-scalp fallback or parallel context veto path is retained.

## Included user stories

- **US-02 — Counterfactual evidence:** every evaluated candidate persists one entry decision and all canonical score contributions.
- **US-12 — Explicit entry routing:** context is scoring information only; the router handles economics and structural timing.
- **US-16 — Deterministic traceability:** confirmed pending lineage is preserved and a satisfied confirmation is not requested twice.

## Canonical score

The candidate score is decomposed as:

```text
base directional score
+ continuous market context contribution
+ READY-only multi-timeframe contribution
+ continuous TP-feasibility contribution
```

Each contribution is journalled independently.

## Market context

Market context is never a veto. The bounded context score combines:

- benchmark session return;
- benchmark momentum;
- market breadth;
- sector participation;
- directional relative strength.

Directional relative strength is the dominant component, so a sufficiently strong symbol can compensate an opposed benchmark.

## Multi-timeframe

Only READY features influence the live score:

- M5: ±4;
- M15: ±6;
- M30: ±2;
- total bounded to ±10.

H1 and PROVISIONAL features remain diagnostic because their maturity or evidence is insufficient.

## TP feasibility

The old soft/hard/severe penalty accumulation is removed. The canonical feasibility score is 0–100 and combines:

- TP versus ATR: 30%;
- TP versus momentum: 25%;
- costs versus TP: 30%;
- movement remaining: 15%.

It becomes a bounded score contribution between −15 and +15. Costs greater than or equal to gross TP remain the only feasibility hard rejection.

## Probability and ranking

`heuristic_v3` retains a raw explainable probability and calibrates it by asset class before calculating net expectancy.

Within a five-point score bucket, ranking uses:

1. calibrated net expected value;
2. expected net profit at TP;
3. exact score.

EV is not a veto.

## Pending lifecycle

- `market_context_opposed` invalidation is removed;
- confirmed candidates carry `entry_origin=pending_confirmation`;
- `structural_confirmation_satisfied=true` prevents a second retest request;
- every evaluated candidate receives exactly one EntryDecision before selection.

## Europe

The unreachable micro-scalp fallback is deleted.

`EU_TREND_BUY_V1` applies to EU BUY candidates:

- TP: 2.0%;
- SL: 1.2%;
- stale horizon: 180 minutes;
- selection threshold: 110;
- EU top N: 1.

EU SELL keeps the standard 1.0% / 0.7% profile and 75-minute stale horizon.

## Data and run finalization

Live market validation uses actual validation time rather than the timestamp captured before broker fetch. Historical/replay validation remains deterministic.

The analysis contract is schema v7. Clean shutdowns write final summaries and finalize both current and archived manifests.

## Removed contracts

- binary context routing and pending vetoes;
- old TP-feasibility penalty categories and caps;
- `eu_micro_scalp_fallback` source and implementation;
- global minimum top-N across asset classes;
- duplicate confirmation routing.

## Non-goals

PR5-B does not add gap handling for workstation sleep, broker-side BUY safety stops, real broker exit fills, drawdown limits or portfolio reconciliation. Those remain pre-live operational work.
