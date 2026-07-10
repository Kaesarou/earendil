from types import SimpleNamespace

from app.journal.daily_summary import DailySummaryAggregator


def test_daily_summary_uses_closed_position_net_pnl_and_removes_best_holds():
    summary = DailySummaryAggregator(journal_detail_level='normal')

    summary.record(
        'decision',
        {
            'symbol': 'AAPL',
            'signal': SimpleNamespace(action='HOLD', reason='market_regime_dead_market'),
            'trade_plan': SimpleNamespace(
                approved=False,
                reason='market_regime_dead_market',
            ),
        },
    )
    summary.record(
        'position_closed',
        {
            'closed_position': SimpleNamespace(
                gross_pnl=10.0,
                estimated_total_cost=1.5,
                net_pnl_estimated=8.5,
            )
        },
    )

    data = summary.to_dict()

    assert data['hold_reasons'] == {'market_regime_dead_market': 1}
    assert 'best_hold_candidates' not in data['rejections']
    assert data['pnl'] == {
        'gross_estimated': 10.0,
        'estimated_total_cost': 1.5,
        'net_estimated': 8.5,
    }
