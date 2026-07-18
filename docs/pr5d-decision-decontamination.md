# PR5-D — Decision decontamination

## Goal

Make the next homogeneous demo run interpretable without changing fixed TP/SL profiles, thresholds, top-N, RiskManager or managed exits.

## Live score

```text
final score
= directional score
+ compressed context [-4, +4]
+ M5 READY [-3, +3]
+ TP feasibility [-15, +15]
```

## Changes

- `market_context_score_v3`: full raw context retained; live contribution is `clip(raw × 0.25, -4, +4)`; freshness no longer gates relative strength.
- `multi_timeframe_score_v2`: M5 READY contributes `+3/-3`; M15, M30 and H1 are diagnostic.
- `tp_feasibility_score_v4`: TP/ATR 35%, TP/momentum 30%, costs/TP 35%, freshness 0% live.
- `heuristic_v5`: removes freshness, M15 and M30; base rates and slope remain unchanged for the next observation.
- live top-N ranking: exact score, then feasibility, then directional score; EV remains journalled.
- `entry_router_v6`: `WAIT_FOR_RETEST` requires usable structure and `extension_percent / effective_TP >= 0.20`.
- schema v9 adds raw/effective context and extension-to-TP evidence.

## Unchanged

- US `1.20 / 0.70 / 60`, threshold 115, top 2;
- EU BUY `2.00 / 1.20 / 180`, EU SELL `1.00 / 0.70 / 75`, threshold 110, top 1;
- crypto support;
- hard economics, session horizon and risk constraints;
- net breakeven, trailing, stale and force close;
- demo-only operation.

## Non-goals

No profile recalibration, EU BUY suspension, timeout probability, dynamic TP, managed-stop change or production-risk implementation.
