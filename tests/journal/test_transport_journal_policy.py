from app.journal.journal_policy import should_write_to_trade_journal


def test_transport_frames_are_not_written_at_normal_detail():
    assert not should_write_to_trade_journal(
        'market_data_event_received',
        {'symbol': 'BTC'},
        'normal',
    )
    assert not should_write_to_trade_journal(
        'rest_control_snapshot',
        {'symbol': 'BTC'},
        'normal',
    )


def test_transport_frames_remain_available_at_full_detail():
    assert should_write_to_trade_journal(
        'market_data_event_received',
        {'symbol': 'BTC'},
        'full',
    )


def test_aggregated_control_event_is_kept_at_normal_detail():
    assert should_write_to_trade_journal(
        'rest_control_completed',
        {'received_symbol_count': 10},
        'normal',
    )
