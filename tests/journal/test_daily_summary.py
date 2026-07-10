from types import SimpleNamespace

from app.execution.candidate_readiness import CandidateReadiness
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


def test_daily_summary_counts_readiness_and_pending_reasons():
    summary = DailySummaryAggregator(journal_detail_level='normal')
    summary.record(
        'candidate_tp_feasibility',
        {
            'evaluated_candidates': [
                SimpleNamespace(
                    readiness=CandidateReadiness.TRADABLE_NOW,
                    readiness_reason='tp_feasibility_ready',
                ),
                SimpleNamespace(
                    readiness=CandidateReadiness.WAIT_CONFIRMATION,
                    readiness_reason='insufficient_runway',
                ),
                SimpleNamespace(
                    readiness=CandidateReadiness.REJECT,
                    readiness_reason='cost_to_tp_absurd',
                ),
            ]
        },
    )
    summary.record('pending_entry_registered', {})
    summary.record('pending_entry_confirmed', {})
    summary.record('pending_entry_expired', {})
    summary.record('pending_entry_invalidated', {})

    data = summary.to_dict()

    assert data['decisions']['tradable_now_total'] == 1
    assert data['decisions']['wait_confirmation_total'] == 1
    assert data['decisions']['rejected_by_feasibility_total'] == 1
    assert data['decisions']['wait_confirmation_by_reason'] == {
        'insufficient_runway': 1
    }
    assert data['pending_entries']['registered'] == 1
    assert data['pending_entries']['confirmed'] == 1
    assert data['pending_entries']['expired'] == 1
    assert data['pending_entries']['invalidated'] == 1


def test_daily_summary_tracks_orders_and_pnl_from_pending():
    summary = DailySummaryAggregator(journal_detail_level='normal')
    candidate = SimpleNamespace(
        signal=SimpleNamespace(
            metadata={'entry_origin': 'pending_confirmation'},
        )
    )

    summary.record(
        'order_submitted',
        {
            'symbol': 'AMAT',
            'candidate': candidate,
        },
    )
    summary.record(
        'position_opened',
        {
            'symbol': 'AMAT',
            'position_id': 'position-1',
            'candidate': candidate,
        },
    )
    summary.record(
        'position_closed',
        {
            'closed_position': SimpleNamespace(
                position_id='position-1',
                amount=1_000.0,
                gross_pnl=12.0,
                estimated_total_cost=3.5,
                net_pnl_estimated=8.5,
            )
        },
    )

    data = summary.to_dict()

    assert data['orders']['from_pending'] == 1
    assert data['pnl']['from_pending'] == 8.5


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
