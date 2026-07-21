from pathlib import Path


REMOVED_SETTING_REFERENCES = (
    'settings.market_data_mode',
    'settings.poll_interval_seconds',
    'settings.market_data_queue_capacity',
    'settings.ws_symbol_silence_seconds',
    'settings.ws_position_silence_seconds',
    'settings.ws_global_silence_seconds',
    'settings.rest_control_interval_seconds',
    'settings.rest_fallback_cooldown_seconds',
    'settings.position_fallback_interval_seconds',
    'settings.candle_clock_grace_seconds',
    'settings.position_reconciliation_grace_seconds',
    'settings.unknown_order_lookup_interval_seconds',
)


def test_main_no_longer_reads_technical_runtime_policy_from_settings():
    source = Path('app/main.py').read_text(encoding='utf-8')

    for removed in REMOVED_SETTING_REFERENCES:
        assert removed not in source
    assert 'from app.runtime.runtime_policy import (' in source
    assert "'mode': 'websocket'" in source
