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
    assert data['schema_version'] == 5
    assert data['market_data']['accepted'] == 3
    assert data['market_data']['trading_snapshots_processed'] == 2
    assert data['market_data']['context_snapshots_accepted'] == 1


def test_analysis_ready_summary_exposes_penalties_and_hard_constraints():
    summary = AnalysisReadySummaryAggregator(run_id='run-test')
    analysis = SimpleNamespace(
        penalty_components=(
            'tp_too_far_vs_atr_severe',
            'movement_already_consumed_hard',
        ),
        hard_rejection_components=('cost_to_tp_absurd_hard_reject',),
        sl_tp_source='fixed',
    )
    evaluated = SimpleNamespace(
        tp_feasibility=analysis,
        effective_sl_tp=SimpleNamespace(source='fixed'),
        candidate=SimpleNamespace(tp_feasibility_metadata={}),
    )

    summary.record(
        'candidate_tp_feasibility',
        {'evaluated_candidates': [evaluated]},
    )
    data = summary.to_dict()

    assert data['tp_feasibility']['penalty_components'] == {
        'tp_too_far_vs_atr_severe': 1,
        'movement_already_consumed_hard': 1,
    }
    assert data['tp_feasibility']['hard_rejection_components'] == {
        'cost_to_tp_absurd_hard_reject': 1,
    }
    assert 'cap_components' not in data['tp_feasibility']
    assert data['effective_sl_tp']['by_source'] == {'fixed': 1}
    assert 'decisions' not in data
