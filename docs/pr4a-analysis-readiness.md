# PR4A — Analysis-ready routing evidence

PR4A is a corrective, deliberately small step between the first post-PR3 collection run and PR5 calibration. It repairs temporal and mathematical inconsistencies found in the 14 July 2026 crypto and European logs without changing fees, score thresholds, TP/SL profiles, the EU micro-scalp policy or multi-timeframe decision rules.

## User stories addressed

- **US-02 — counterfactual evidence readiness:** every evaluated entry is emitted with stable, denormalized fields that can be joined to future M1 candles without rebuilding the runtime object graph.
- **US-16 — deterministic traceability and no-lookahead:** model versions and the source commit are recorded, and market context is evaluated at the snapshot actually available when the decision is made.

## Root causes confirmed from the first post-PR3 run

### Market context was evaluated at the wrong instant

A closed M1 bar may end at `10:32:00`, while the accepted broker snapshot that triggers its processing arrives several seconds later. The previous routing code asked the context service for a view as of the candle close. Fresh snapshots from the same decision cycle could therefore appear to be in the future and turn benchmark and breadth context into `unknown`.

PR4A uses the accepted decision snapshot timestamp for market context. Multi-timeframe context continues to use the closed-candle timestamp, so only complete bars at or before the candidate are visible.

### Severe feasibility and retest eligibility shared the same penalty

The former formula was:

```text
feasibility runway = 100 - 2 × feasibility penalty
severe penalty     = 40
minimum retest runway = 25
```

A severe penalty therefore implied a runway of at most 20, making `WAIT_FOR_RETEST` unreachable exactly when the router was supposed to consider a better entry.

PR4A separates the two concepts:

- feasibility runway remains diagnostic evidence about the current entry;
- structural retest score comes from the existing late-entry structure quality (`GOOD`, `ACCEPTABLE`, `POOR`);
- hard economic or strategy rejection still produces `SKIP` immediately;
- a moderately extended candidate with usable structure may become `WAIT_FOR_RETEST` and is fully recalculated after confirmation.

No candidate bypasses fee-aware economics or hard rejection.

## Analysis-ready entry records

Each `entry_decision` event now exposes the following top-level fields in addition to the complete serialized objects:

- `candidate_id` and optional `origin_candidate_id`;
- candidate timestamp, symbol and side;
- reference entry price;
- effective SL and TP percentages;
- estimated total cost and expected net profit percentages;
- score and base score;
- entry action and reason;
- selection outcome and rejection reason;
- market-context, multi-timeframe and entry-router model versions.

This is sufficient for external candidate-to-M1 labelling of TP-before-SL, SL-before-TP, timeout, MFE, MAE and net-return scenarios. PR4A does not add a replay engine to Goblin.

## Summary schema v4

Partial and final summaries now distinguish:

- all snapshots accepted by batch validation;
- trading snapshots actually processed by symbol strategies;
- accepted context-only benchmark snapshots;
- pre-router compatibility readiness from authoritative `ENTER_NOW`, `WAIT_FOR_RETEST` and `SKIP` decisions;
- TP-feasibility penalty, cap and hard-rejection components;
- effective SL/TP sources and applied adaptations.

The misleading `tradable_now_total` key is replaced by `pre_entry_router_tradable_total`.

## Source traceability on Linux

Start the Docker runtime with:

```bash
bash scripts/start_goblin.sh
```

The launcher exports the current Git commit as the Docker build argument consumed by `run_manifest.py`. The source fingerprint remains an independent fallback and integrity signal.

## Explicit non-goals

PR4A does not:

- change fee assumptions or baseline TP/SL values;
- recalibrate the score or feasibility penalties;
- change EU micro-scalp eligibility;
- activate multi-timeframe features in routing;
- implement maturity tiers;
- add a broker simulator, replay runtime or champion/challenger framework.

## PR4B decision gate

After complete crypto, European and US sessions with PR4A logs, decide whether a PR4B is necessary. The accepted candidate for PR4B is multi-timeframe maturity:

| Timeframe | Provisional | Ready |
|---|---:|---:|
| M1 | 10 bars | 20 bars |
| M5 | 8 bars | 15 bars |
| M15 | 6 bars | 12 bars |
| M30 | 5 bars | 10 bars |
| H1 | 5 bars | 8 bars |

`PROVISIONAL` features would be journalled but could not hard-reject a candidate. `READY` features would use timeframe-specific EMA, ATR, range and compression windows. This remains outside PR4A so the next run isolates the two confirmed routing defects.

## Path to PR5

1. Run PR4A in eToro demo across crypto, EU and US sessions.
2. Archive all evidence in `goblin-logs`.
3. Label every candidate externally against its future M1 path.
4. Compare current routing with MTF, benchmark, range, score and retest alternatives.
5. Implement only supported changes in **PR5 — First real calibration**.
