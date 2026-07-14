from types import SimpleNamespace

from app.journal.analysis_ready_summary import AnalysisReadySummaryAggregator


def test_analysis_ready_summary_distinguishes_context_and_trading_snapshots():
    summary = AnalysisReadySummaryAggregator(run_id='run-test')

    summary.record(
        'market_batch_validated',
        {'batch': SimpleNamespace(accepted={'AAPL': object(), 'MSFT': object(), 'SPX500': object()})},
    )
    summary.record('market_snapshot', {'symbol': 'AAPL'})
    summary.record('market_snapshot', {'symbol': 'MSFT'})

    data = summary.to_dict()

    assert data['schema_version'] == 4
    assert data['market_data']['accepted'] == 3
    assert data['market_data']['trading_snapshots_processed'] == 2
    assert data['market_data']['context_snapshots_accepted'] == 1


def test_analysis_ready_summary_exposes_feasibility_components_and_truthful_readiness_name():
    summary = AnalysisReadySummaryAggregator(run_id='run-test')
    analysis = SimpleNamespace(
        penalty_components=('tp_too_far_vs_atr_severe', 'near_recent_extreme'),
        cap_components=('tp_atr_severe_cap',),
        hard_rejection_components=(),
        sl_tp_source='fixed',
    )
    evaluated = SimpleNamespace(
        readiness=SimpleNamespace(value='tradable_now'),
        readiness_reason='entry_decision_required',
        tp_feasibility=analysis,
        effective_sl_tp=SimpleNamespace(source='fixed'),
        candidate=SimpleNamespace(tp_feasibility_metadata={}),
    )

    summary.record(
        'candidate_tp_feasibility',
        {'evaluated_candidates': [evaluated]},
    )
    data = summary.to_dict()

    assert 'tradable_now_total' not in data['decisions']
    assert data['decisions']['pre_entry_router_tradable_total'] == 1
    assert data['tp_feasibility']['penalty_components'] == {
        'tp_too_far_vs_atr_severe': 1,
        'near_recent_extreme': 1,
    }
    assert data['tp_feasibility']['cap_components'] == {
        'tp_atr_severe_cap': 1,
    }
    assert data['effective_sl_tp']['by_source'] == {'fixed': 1}
