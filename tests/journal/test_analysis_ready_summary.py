from types import SimpleNamespace

from app.journal.analysis_ready_summary import (
    AnalysisReadySummaryAggregator,
)


def test_analysis_ready_summary_distinguishes_context_and_trading_snapshots():
    summary = AnalysisReadySummaryAggregator(run_id='run-test')
    summary.record(
        'market_batch_validated',
        {
            'batch': SimpleNamespace(
                accepted={
                    'AAPL': object(),
                    'MSFT': object(),
                    'SPX500': object(),
                }
            )
        },
    )
    summary.record('market_snapshot', {'symbol': 'AAPL'})
    summary.record('market_snapshot', {'symbol': 'MSFT'})

    data = summary.to_dict()
    assert data['schema_version'] == 7
    assert data['market_data']['accepted'] == 3
    assert data['market_data']['trading_snapshots_processed'] == 2
    assert data['market_data']['context_snapshots_accepted'] == 1


def test_analysis_ready_summary_exposes_continuous_scores_and_hard_constraints():
    summary = AnalysisReadySummaryAggregator(run_id='run-test')
    analysis = SimpleNamespace(
        feasibility_score=24.0,
        score_contribution=-7.8,
        hard_rejection_components=('cost_to_tp_absurd_hard_reject',),
        sl_tp_source='eu_trend_buy_v1',
    )
    candidate = SimpleNamespace(
        market_context_score=6.0,
        multi_timeframe_score=4.0,
        net_expected_value_percent=-0.12,
    )
    evaluated = SimpleNamespace(
        tp_feasibility=analysis,
        effective_sl_tp=SimpleNamespace(source='eu_trend_buy_v1'),
        candidate=candidate,
    )

    summary.record(
        'candidate_tp_feasibility',
        {'evaluated_candidates': [evaluated]},
    )
    data = summary.to_dict()

    assert data['tp_feasibility']['hard_rejection_components'] == {
        'cost_to_tp_absurd_hard_reject': 1,
    }
    assert data['effective_sl_tp']['by_source'] == {
        'eu_trend_buy_v1': 1,
    }
    contributions = data['score_contributions']
    assert sum(contributions['market_context'].values()) == 1
    assert sum(contributions['multi_timeframe'].values()) == 1
    assert sum(contributions['tp_feasibility_score'].values()) == 1
    assert sum(
        contributions['tp_feasibility_contribution'].values()
    ) == 1
    assert sum(contributions['net_expected_value_percent'].values()) == 1
    assert 'penalty_components' not in data['tp_feasibility']
    assert 'decisions' not in data
