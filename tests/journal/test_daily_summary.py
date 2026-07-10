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


def test_daily_summary_calculates_net_pnl_when_estimated_costs_are_available():
    summary = DailySummaryAggregator(journal_detail_level='normal')

    summary.record(
        'position_closed',
        {
            'closed_position': SimpleNamespace(
                amount=1_000.0,
                gross_pnl=12.0,
                estimated_total_cost_percent=0.35,
            )
        },
    )

    pnl = summary.to_dict()['pnl']
    assert pnl['gross_estimated'] == 12.0
    assert pnl['estimated_costs'] == 3.5
    assert pnl['net_estimated'] == 8.5
    assert pnl['net_estimated_available'] is True


def test_daily_summary_does_not_fake_net_pnl_when_costs_are_unavailable():
    summary = DailySummaryAggregator(journal_detail_level='normal')

    summary.record(
        'position_closed',
        {
            'closed_position': SimpleNamespace(
                amount=1_000.0,
                gross_pnl=12.0,
            )
        },
    )

    pnl = summary.to_dict()['pnl']
    assert pnl['gross_estimated'] == 12.0
    assert pnl['estimated_costs'] is None
    assert pnl['net_estimated'] is None
    assert pnl['net_estimated_available'] is False
