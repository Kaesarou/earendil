# PR5-A — De-harden probabilistic signals

## Goal

PR5-A applies the first evidence-backed calibration from the 2026-07-14 crypto, EU and US runs.

The decision model now separates:

- **hard constraints**, which make a trade invalid or non-executable;
- **probabilistic signals**, which reduce or increase confidence but cannot veto a trade by themselves.

This is a deliberate contract replacement. No compatibility aliases, legacy fields or parallel decision paths are retained.

## Included user stories

- **US-02 — Counterfactual evidence:** retain enough candidate economics, routing and expectancy data to label rejected and accepted setups after the run.
- **US-12 — Explicit entry routing:** distinguish an economic hard rejection from a probabilistic penalty or a request for a structural retest.
- **US-16 — Deterministic traceability:** preserve the PR4B candidate and pending lineage while changing the decision model without lookahead.

## Hard constraints retained

A candidate may still be rejected when:

- its expected net profit is below the configured minimum after estimated costs;
- estimated costs are greater than or equal to the gross take-profit distance;
- required market data is invalid;
- a pending structure is invalidated;
- the session no longer allows a new entry;
- the risk manager cannot approve the plan;
- order sizing or broker execution fails.

## Probabilistic signals

The following remain observable and may reduce the candidate score or require a retest, but do not create a standalone hard rejection:

- benchmark and market-context opposition;
- breadth and sector context;
- symbol relative strength;
- ATR distance to the target;
- target distance versus recent momentum;
- movement already consumed;
- move extension and deceleration;
- close quality and SELL-specific setup quality.

## Removed contracts

PR5-A removes rather than deprecates:

- `context_opposition_is_hard_reject`;
- severe-extension and severe-feasibility `SKIP` branches;
- `near_recent_extreme` and its configuration;
- late-entry, SELL and TP-feasibility score caps;
- late-entry and SELL rejection fields;
- TP-feasibility `cap_components`;
- the diagnostic `WAIT_CONFIRMATION` readiness state.

The canonical candidate score is now the base setup score minus explicit probabilistic penalties. There is no hidden cap below the selection threshold.

## Market context routing

Market-context opposition no longer returns `SKIP`.

For the transitional PR5-A policy:

- positive directional relative strength compensates an opposed context;
- opposed context without positive directional relative strength requests `WAIT_FOR_RETEST` when a usable structural retest exists;
- opposed context alone never rejects a candidate.

The exact benchmark, breadth, sector and relative-strength weight matrix remains a PR5-B calibration task after the next run.

## Pending spread behavior

A spread above the execution limit now:

1. emits `pending_entry_confirmation_blocked`;
2. keeps the pending setup alive;
3. increments its observed-candle age;
4. allows normal expiry at the configured limit.

It no longer invalidates the structural thesis. Spread validation still applies before actual execution through the risk layer.

## Diagnostic net expectancy

The TP-probability model is versioned as `heuristic_v2` and now logs:

- estimated TP-before-SL probability;
- break-even probability after estimated costs;
- net expected value percentage;
- probability edge over break-even.

These values are diagnostic only in PR5-A. They do not select or reject a candidate.

## Deliberate non-goals

PR5-A does not change:

- selection thresholds (`100` dynamic US and `115` default);
- TP or SL profiles;
- fee assumptions;
- position sizing or portfolio risk limits;
- the top-N selection rule;
- pending duration or confirmation criteria;
- MTF influence on live decisions;
- watchlists;
- the probability estimator into a calibrated model;
- the market-context contribution weight matrix.

## PR5-B evidence backlog

After the first full PR5-A run, PR5-B design will evaluate:

1. benchmark/breadth/sector/relative-strength weight matrix, including the remaining treatment of opposed context;
2. MTF `READY` and `PROVISIONAL` contributions to score and routing;
3. whether net expected value should become a selection criterion;
4. probability-model calibration against TP-before-SL labels;
5. pending duration and confirmation thresholds by asset class;
6. effect of temporary spread blocks on confirmation and eventual outcomes;
7. selection thresholds and top-N behavior;
8. EU micro-scalp usefulness after removal of hidden caps;
9. TP/SL profiles only if post-cost outcome evidence supports a change.

## Validation expectations

The next run must show:

- `entry_router_v4`;
- `heuristic_v2`;
- no `market_context_opposed` hard rejection;
- no `near_recent_extreme` component;
- no score-cap fields or cap components;
- `pending_entry_confirmation_blocked` rather than spread invalidation;
- expectancy fields on standalone `entry_decision` events.
