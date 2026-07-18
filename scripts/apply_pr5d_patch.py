from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def repl(path: str, old: str, new: str, count: int | None = 1) -> None:
    content = read(path)
    found = content.count(old)
    if found == 0 or (count is not None and found != count):
        raise RuntimeError(f'{path}: expected {count}, found {found}: {old[:100]!r}')
    write(path, content.replace(old, new, -1 if count is None else count))


# Live weights and retest threshold.
for old, new in (
    ('tp_vs_atr_weight: float = 0.30', 'tp_vs_atr_weight: float = 0.35'),
    ('tp_vs_momentum_weight: float = 0.25', 'tp_vs_momentum_weight: float = 0.30'),
    ('cost_vs_tp_weight: float = 0.30', 'cost_vs_tp_weight: float = 0.35'),
    ('entry_freshness_weight: float = 0.15', 'entry_freshness_weight: float = 0.0'),
    ('moderate_extension_percent: float = 0.12', 'minimum_extension_to_tp_ratio: float = 0.20'),
):
    repl('app/instruments/models.py', old, new)

# Context v3: rich raw evidence, compressed live contribution, no freshness gate.
path = 'app/execution/scoring/market_context_scorer.py'
repl(path, "MARKET_CONTEXT_SCORER_VERSION = 'market_context_score_v2'", "MARKET_CONTEXT_SCORER_VERSION = 'market_context_score_v3'")
repl(path, '    maximum_absolute_score: float = 15.0\n', '    maximum_absolute_raw_score: float = 15.0\n    effective_score_scale: float = 0.25\n    maximum_absolute_effective_score: float = 4.0\n')
repl(path, '        entry_freshness_score=entry_freshness_score,\n', '')
repl(path, '''    components = {
        'benchmark_session': round(benchmark_session, 4),
        'benchmark_momentum': round(benchmark_momentum, 4),
        'breadth': round(breadth, 4),
        'sector': round(sector, 4),
        'market_background': round(market_background, 4),
        'relative_strength_raw': round(relative_strength_raw, 4),
        'relative_strength_adjustment': round(
            relative_strength_adjustment,
            4,
        ),
    }
    score = _clamp(
        market_background + relative_strength_adjustment,
        -config.maximum_absolute_score,
        config.maximum_absolute_score,
    )
    return MarketContextScore(
        score=round(score, 4),
''', '''    raw_score = _clamp(
        market_background + relative_strength_adjustment,
        -config.maximum_absolute_raw_score,
        config.maximum_absolute_raw_score,
    )
    score = _clamp(
        raw_score * config.effective_score_scale,
        -config.maximum_absolute_effective_score,
        config.maximum_absolute_effective_score,
    )
    components = {
        'benchmark_session': round(benchmark_session, 4),
        'benchmark_momentum': round(benchmark_momentum, 4),
        'breadth': round(breadth, 4),
        'sector': round(sector, 4),
        'market_background': round(market_background, 4),
        'relative_strength_raw': round(relative_strength_raw, 4),
        'relative_strength_adjustment': round(relative_strength_adjustment, 4),
        'raw_market_context_score': round(raw_score, 4),
        'effective_market_context_contribution': round(score, 4),
    }
    return MarketContextScore(
        score=round(score, 4),
''')
repl(path, '''            'finalized_with_entry_freshness': (
                entry_freshness_score is not None
            ),
''', '''            'raw_market_context_score': round(raw_score, 4),
            'effective_market_context_contribution': round(score, 4),
            'effective_score_scale': config.effective_score_scale,
            'entry_freshness_used_in_live_score': False,
''')
repl(path, '''    entry_freshness_score: float | None,
    config: MarketContextScoreConfig,
) -> float:
    freshness = _freshness_factor(entry_freshness_score)
    gated_adjustment = raw_adjustment * freshness
    if gated_adjustment >= 0:
''', '''    config: MarketContextScoreConfig,
) -> float:
    if raw_adjustment >= 0:
''')
repl(path, '        return min(gated_adjustment, maximum_positive)\n', '        return min(raw_adjustment, maximum_positive)\n')
repl(path, '        gated_adjustment,\n', '        raw_adjustment,\n')
repl(path, "        'relative_strength_adjustment': 0.0,\n", "        'relative_strength_adjustment': 0.0,\n        'raw_market_context_score': 0.0,\n        'effective_market_context_contribution': 0.0,\n")

# MTF v2: M5 live only; M15/M30 remain present with zero weight.
path = 'app/execution/scoring/multi_timeframe_scorer.py'
repl(path, "MULTI_TIMEFRAME_SCORER_VERSION = 'multi_timeframe_score_v1'", "MULTI_TIMEFRAME_SCORER_VERSION = 'multi_timeframe_score_v2'")
repl(path, "    'm5': 4.0,\n    'm15': 6.0,\n    'm30': 2.0,\n", "    'm5': 3.0,\n    'm15': 0.0,\n    'm30': 0.0,\n")
repl(path, '_MAXIMUM_ABSOLUTE_SCORE = 10.0', '_MAXIMUM_ABSOLUTE_SCORE = 3.0')
repl(path, '''        ready_timeframes.append(timeframe)
        components[timeframe] = _direction_component(
''', '''        ready_timeframes.append(timeframe)
        if weight == 0.0:
            continue
        components[timeframe] = _direction_component(
''')
repl(path, "            'ready_alignment': context.ready_alignment.value,\n", "            'ready_alignment': context.ready_alignment.value,\n            'live_timeframes': ['m5'],\n            'diagnostic_timeframes': ['m15', 'm30', 'h1'],\n")

# TP feasibility and probability model versions/inputs.
repl('app/execution/scoring/tp_feasibility.py', "TP_FEASIBILITY_MODEL_VERSION = 'tp_feasibility_score_v3'", "TP_FEASIBILITY_MODEL_VERSION = 'tp_feasibility_score_v4'")
path = 'app/execution/scoring/tp_probability.py'
repl(path, "TP_PROBABILITY_MODEL_VERSION = 'heuristic_v4'", "TP_PROBABILITY_MODEL_VERSION = 'heuristic_v5'")
repl(path, '    maximum_context_score: float = 15.0\n    maximum_multi_timeframe_score: float = 10.0\n', '    maximum_context_score: float = 4.0\n    maximum_multi_timeframe_score: float = 3.0\n')
repl(path, '''            'entry_freshness_score': _bounded(
                tp_feasibility.entry_freshness_score, 0.0, 100.0
            ),
''', '')
repl(path, '''        raw_score = (
            0.14 * scores['cost_score']
            + 0.12 * scores['atr_distance_score']
            + 0.16 * scores['momentum_distance_score']
            + 0.14 * scores['entry_freshness_score']
            + 0.10 * scores['trend_score']
            + 0.08 * scores['close_quality_score']
            + 0.06 * scores['regime_score']
            + 0.10 * scores['market_context_score']
            + 0.10 * scores['multi_timeframe_score']
        )
''', '''        raw_score = (
            0.20 * scores['cost_score']
            + 0.17 * scores['atr_distance_score']
            + 0.22 * scores['momentum_distance_score']
            + 0.14 * scores['trend_score']
            + 0.10 * scores['close_quality_score']
            + 0.07 * scores['regime_score']
            + 0.04 * scores['market_context_score']
            + 0.06 * scores['multi_timeframe_score']
        )
''')

# Ranking no longer lets uncalibrated EV override exact score.
path = 'app/execution/candidate_selector.py'
repl(path, 'import math\n', '')
repl(path, '''def _evaluated_candidate_ranking_key(
    evaluated_candidate: EvaluatedTradeCandidate,
) -> tuple[float, float, float, float]:
    candidate = evaluated_candidate.candidate
    score = candidate.score
    score_bucket = math.floor(score / 5) * 5
    net_expected_value = candidate.net_expected_value_percent
    return (
        score_bucket,
        net_expected_value if net_expected_value is not None else -999.0,
        evaluated_candidate.economics.expected_net_profit,
        score,
    )
''', '''def _evaluated_candidate_ranking_key(
    evaluated_candidate: EvaluatedTradeCandidate,
) -> tuple[float, float, float]:
    candidate = evaluated_candidate.candidate
    feasibility_score = (
        candidate.tp_feasibility_score
        if candidate.tp_feasibility_score is not None
        else -1.0
    )
    return candidate.score, feasibility_score, candidate.directional_score
''')

# Router v6: extension is measured relative to the effective TP.
path = 'app/execution/entry_decision.py'
repl(path, "ENTRY_DECISION_MODEL_VERSION = 'entry_router_v5'", "ENTRY_DECISION_MODEL_VERSION = 'entry_router_v6'")
repl(path, '''        extension_percent, retest_level = _extension_from_reference(candidate)
        structural_retest_score = _structural_retest_score(candidate)
        retest_eligible = (
            retest_level is not None
            and extension_percent is not None
            and extension_percent >= config.moderate_extension_percent
            and structural_retest_score
            >= config.minimum_structural_retest_score
        )
''', '''        extension_percent, retest_level = _extension_from_reference(candidate)
        effective_take_profit_percent = _effective_take_profit_percent(
            evaluated_candidate
        )
        extension_to_tp_ratio = _ratio(
            extension_percent,
            effective_take_profit_percent,
        )
        structural_retest_score = _structural_retest_score(candidate)
        retest_eligible = (
            retest_level is not None
            and extension_to_tp_ratio is not None
            and extension_to_tp_ratio >= config.minimum_extension_to_tp_ratio
            and structural_retest_score
            >= config.minimum_structural_retest_score
        )
''')
repl(path, '''                'extension_percent': _round_optional(extension_percent),
                'retest_level': _round_optional(retest_level),
''', '''                'extension_percent': _round_optional(extension_percent),
                'effective_take_profit_percent': _round_optional(
                    effective_take_profit_percent
                ),
                'extension_to_tp_ratio': _round_optional(extension_to_tp_ratio),
                'minimum_extension_to_tp_ratio': (
                    config.minimum_extension_to_tp_ratio
                ),
                'retest_level': _round_optional(retest_level),
''')
repl(path, 'def _structural_retest_score(candidate) -> float:\n', '''def _effective_take_profit_percent(
    evaluated_candidate: EvaluatedTradeCandidate,
) -> float | None:
    value = getattr(
        evaluated_candidate.tp_feasibility,
        'effective_take_profit_percent',
        None,
    )
    if value is None:
        value = getattr(
            evaluated_candidate.economics,
            'effective_take_profit_percent',
            None,
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _structural_retest_score(candidate) -> float:
''')

# Analysis schema v9.
repl('app/journal/run_manifest.py', "        'schema_version': 8,", "        'schema_version': 9,")
repl('app/journal/run_manifest.py', "                'market_context_score',\n", "                'market_context_score',\n                'raw_market_context_score',\n                'effective_market_context_contribution',\n")
repl('app/journal/run_manifest.py', "                'entry_route_reason',\n", "                'entry_route_reason',\n                'extension_to_tp_ratio',\n")
repl('app/journal/daily_summary.py', "            'schema_version': 6,", "            'schema_version': 9,")

# Active README contract.
path = 'README.md'
for old, new in (
    ('freshness-gated relative-strength scoring', 'compressed relative-strength scoring'),
    ('TP-aware feasibility and entry-freshness scoring', 'three-factor TP feasibility with diagnostic entry freshness'),
    ('+ freshness-gated market-context contribution', '+ compressed market-context contribution [-4, +4]'),
    ('+ READY multi-timeframe contribution', '+ READY M5 contribution [-3, +3]'),
    ('It is a probabilistic input, never a standalone veto.', 'It is retained for diagnosis and counterfactual analysis, but has no live score or probability weight.'),
    ('A contrary benchmark is never a veto. Context is bounded to `[-15, +15]`.', 'A contrary benchmark is never a veto. The raw context remains bounded to `[-15, +15]`; its live contribution is `clip(raw × 0.25, -4, +4)`.'),
    ('| M5 | +4 | -4 |', '| M5 | +3 | -3 |'),
    ('| M15 | +6 | -6 |', '| M15 | 0 | 0 |'),
    ('| M30 | +2 | -2 |', '| M30 | 0 | 0 |'),
    ('The total remains bounded to `[-10, +10]`. These initial weights are calibration parameters, not proven constants.', 'Only M5 affects the live score, bounded to `[-3, +3]`. M15, M30 and H1 remain fully journalled diagnostics.'),
    ('`tp_feasibility_score_v3` combines:', '`tp_feasibility_score_v4` combines:'),
    ('| TP versus ATR | 30% |', '| TP versus ATR | 35% |'),
    ('| TP versus recent momentum | 25% |', '| TP versus recent momentum | 30% |'),
    ('| Estimated costs versus TP | 30% |', '| Estimated costs versus TP | 35% |'),
    ('| TP-aware entry freshness | 15% |', '| TP-aware entry freshness | 0% — diagnostic only |'),
    ('`heuristic_v4` uses direct components once each:', '`heuristic_v5` uses direct components once each:'),
    ('- entry freshness;\n', ''),
    ('- READY MTF.\n', '- READY M5.\n'),
    ('EV ranks candidates inside the same five-point score bucket but is not a veto.', 'EV remains diagnostic and is not a veto. Live ranking uses exact score, then TP feasibility, then directional score.'),
    ('PR5-C uses summary and run-manifest schema **v8**.', 'PR5-D uses summary and run-manifest schema **v9**.'),
):
    repl(path, old, new)

write('docs/pr5d-decision-decontamination.md', '''# PR5-D — Decision decontamination

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
''')

# Existing tests: update expected active contract without deleting historical fixtures.
path = 'tests/execution/scoring/test_market_context_scorer.py'
repl(path, 'def test_consumed_move_limits_positive_relative_strength_compensation():', 'def test_freshness_is_diagnostic_for_context_scoring():')
repl(path, '''    assert fresh.score > consumed.score
    assert consumed.score < 0
    assert preliminary.components['relative_strength_adjustment'] == 0.0
''', '''    assert fresh.score == consumed.score == preliminary.score
    assert fresh.components == consumed.components == preliminary.components
    assert consumed.diagnostics['entry_freshness_used_in_live_score'] is False
''')
repl(path, '    assert -15.0 <= extreme.score <= 15.0\n', '    assert -4.0 <= extreme.score <= 4.0\n')

path = 'tests/execution/scoring/test_multi_timeframe_scorer.py'
repl(path, 'def test_ready_m5_m15_m30_contribute_with_documented_weights():', 'def test_only_ready_m5_contributes_to_live_score():')
repl(path, "    assert result.components == {'m5': 4.0, 'm15': 6.0, 'm30': -2.0}\n    assert result.score == 8.0\n", "    assert result.components == {'m5': 3.0, 'm15': 0.0, 'm30': 0.0}\n    assert result.score == 3.0\n")
repl(path, '    assert buy.score == -10.0\n    assert sell.score == 10.0\n', '    assert buy.score == -3.0\n    assert sell.score == 3.0\n')

path = 'tests/execution/test_candidate_selector.py'
repl(path, 'def test_calibrated_ev_breaks_ties_inside_same_score_bucket():', 'def test_exact_score_ranks_before_diagnostic_ev():')
repl(path, "        'HIGH_EV',\n        'LOW_EV',\n", "        'LOW_EV',\n        'HIGH_EV',\n")

path = 'tests/execution/test_entry_decision.py'
repl(path, '''        tp_feasibility=SimpleNamespace(
            tp_feasibility_hard_rejection_reason=(
                hard_rejection_reason
            )
        ),
''', '''        tp_feasibility=SimpleNamespace(
            tp_feasibility_hard_rejection_reason=(
                hard_rejection_reason
            ),
            effective_take_profit_percent=1.0,
        ),
''')

path = 'tests/journal/test_run_manifest.py'
for old, new in (
    ('test_run_manifest_captures_pr5c_contract_without_broker_secrets', 'test_run_manifest_captures_pr5d_contract_without_broker_secrets'),
    ("manifest['schema_version'] == 8", "manifest['schema_version'] == 9"),
    ("'entry_router_v5'", "'entry_router_v6'"),
    ("'market_context_score_v2'", "'market_context_score_v3'"),
    ("'multi_timeframe_score_v1'", "'multi_timeframe_score_v2'"),
    ("'tp_feasibility_score_v3'", "'tp_feasibility_score_v4'"),
    ("'heuristic_v4'", "'heuristic_v5'"),
):
    repl(path, old, new)
repl(path, "        'market_context_score',\n", "        'market_context_score',\n        'raw_market_context_score',\n        'effective_market_context_contribution',\n")
repl(path, "        'entry_freshness_score',\n", "        'entry_freshness_score',\n        'extension_to_tp_ratio',\n")
repl('tests/journal/test_daily_summary.py', "data['schema_version'] == 6", "data['schema_version'] == 9")
repl('tests/execution/scoring/test_tp_probability.py', 'test_candidate_probability_persists_v4_evidence_without_score_change', 'test_candidate_probability_persists_v5_evidence_without_score_change')
repl('tests/execution/scoring/test_tp_probability.py', "== 'heuristic_v4'", "== 'heuristic_v5'")

# Replace active model assertions in any remaining tests.
for test in (ROOT / 'tests').rglob('*.py'):
    content = test.read_text(encoding='utf-8')
    updated = (content
        .replace('market_context_score_v2', 'market_context_score_v3')
        .replace('multi_timeframe_score_v1', 'multi_timeframe_score_v2')
        .replace('tp_feasibility_score_v3', 'tp_feasibility_score_v4')
        .replace('heuristic_v4', 'heuristic_v5')
        .replace('entry_router_v5', 'entry_router_v6'))
    if updated != content:
        test.write_text(updated, encoding='utf-8')

print('PR5-D patch applied.')
