from types import SimpleNamespace

from app.journal.daily_summary import DailySummaryAggregator


def test_daily_summary_counts_candidate_selection_and_rejection_reasons():
    summary = DailySummaryAggregator(journal_detail_level='normal')
    selected = SimpleNamespace(
        symbol='AMZN',
        signal=SimpleNamespace(action='BUY'),
        score=132.4,
        rank_reason='bullish_breakout',
    )
    rejected = SimpleNamespace(
        candidate=SimpleNamespace(
            symbol='AMD',
            signal=SimpleNamespace(action='SELL'),
            score=165.95,
            rank_reason='bearish_breakdown',
        ),
        reason='cooldown_blocked',
    )

    summary.record(
        'candidate_selection',
        {
            'selected_candidates': [selected],
            'rejected_candidates': [rejected],
        },
    )

    data = summary.to_dict()
    assert data['decisions']['selected_total'] == 1
    assert data['decisions']['rejected_total'] == 1
    assert data['rejections']['by_reason'] == {'cooldown_blocked': 1}
    assert data['selected_candidates'][0]['symbol'] == 'AMZN'
    assert data['rejections']['top_rejected_candidates'][0]['symbol'] == 'AMD'
    assert 'best_hold_candidates' not in data['rejections']


def test_daily_summary_uses_estimated_net_pnl_from_closed_position():
    summary = DailySummaryAggregator(journal_detail_level='normal')

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

    assert summary.to_dict()['pnl'] == {
        'gross_estimated': 10.0,
        'estimated_total_cost': 1.5,
        'net_estimated': 8.5,
    }
