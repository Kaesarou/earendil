# PR4B — MTF maturity, lineage and decision observability

PR4B closes the analysis-readiness work started by PR4A. It changes the data contract deliberately and does not preserve the former field names: Goblin is not in production, so the new contract replaces the old one instead of accumulating aliases and compatibility branches.

## Included user stories

- **US-02 — counterfactual identity and decision evidence:** every reconstructed candidate is linked to the initial candidate and the stable pending entry that produced it.
- **US-12 — explicit entry routing:** routing readiness, final selection, risk approval and order execution are reported as separate pipeline stages.
- **US-16 — deterministic traceability and no-lookahead:** MTF evidence uses only closed bars at or before the candidate timestamp, with explicit model and schema versions.
- **Multi-timeframe diagnostic context:** M1/M5/M15/M30/H1 expose explicit maturity and timeframe-specific windows so later calibration can compare their value without changing live decisions.

## Multi-timeframe maturity

Each timeframe has one of three states:

- `unavailable`: insufficient complete bars;
- `provisional`: short-sample direction and returns are available, but full indicators remain null;
- `ready`: all indicators for that timeframe use their complete configured window.

| Timeframe | Provisional | Ready | EMA fast/slow | ATR | Range | Compression |
|---|---:|---:|---:|---:|---:|---:|
| M1 | 10 | 20 | 3/8 | 14 | 20 | 10 |
| M5 | 8 | 15 | 3/8 | 10 | 15 | 8 |
| M15 | 6 | 12 | 3/6 | 8 | 12 | 6 |
| M30 | 5 | 10 | 3/6 | 8 | 10 | 6 |
| H1 | 5 | 8 | 2/5 | 5 | 8 | 5 |

A provisional context is evidence only. PR4B does not add MTF contributions to score, entry routing, risk or execution.

Two alignment views are retained:

- `ready_alignment`: ready timeframes only;
- `alignment_including_provisional`: exploratory view for offline analysis.

There is no warm-start from historical files and no synthetic bar. Only complete bars already observed by the running process are eligible.

## Candidate and pending lineage

The lineage contract is top-level and no longer hidden in signal metadata:

- `candidate_id`: one concrete evaluation;
- `origin_candidate_id`: the initial candidate that opened the chain;
- `pending_entry_id`: stable identifier for the waiting/retest lifecycle.

A candidate reconstructed after confirmation receives a new `candidate_id` while preserving the same `origin_candidate_id` and `pending_entry_id`.

Every pending lifecycle event exposes these identifiers, including registration, refresh, retest detection, confirmation, invalidation and expiry.

## Decision pipeline

`ENTER_NOW` is removed. The router action is now `READY_FOR_SELECTION`, because candidate selection can still reject a timing-valid candidate.

The summary schema v5 reports distinct stages:

1. `READY_FOR_SELECTION / WAIT_FOR_RETEST / SKIP`;
2. selection selected or rejected;
3. risk approved or rejected;
4. order submitted, filled or failed.

This is a semantic clarification only. It does not loosen or tighten any live rule.

## Pending invalidation evidence

A spread invalidation records:

- observed spread and configured maximum;
- bid, ask and last;
- observation timestamp and number of candles observed;
- candidate, origin and pending identifiers.

The summary distinguishes unique pending entries from event counts, and aggregates invalidations by reason, symbol and spread statistics.

PR4B does not change the current behavior that invalidates a pending on excessive spread. That decision belongs to PR5 and must be calibrated from the newly recorded evidence.

## Deliberate non-goals

PR4B does not change:

- benchmark or market-context vetoes;
- score thresholds or score components;
- fees, TP or SL profiles;
- EU micro-scalping;
- pending confirmation or spread behavior;
- watchlists;
- probability or expected-value models;
- risk limits or broker execution.

## Path to PR5

After one or more complete PR4B sessions, offline analysis can compare:

- ready and provisional MTF alignment;
- benchmark and relative strength;
- initial versus retest entries;
- spread invalidations;
- every routing, selection and risk transition.

PR5 will then separate true hard constraints from probabilistic signals and apply only changes supported by observed net outcomes.
