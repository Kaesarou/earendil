from pathlib import Path


def test_main_no_longer_references_removed_market_data_settings():
    source = Path('app/main.py').read_text(encoding='utf-8')

    assert 'settings.ws_symbol_silence_seconds' not in source
    assert 'settings.rest_fallback_cooldown_seconds' not in source
    assert 'settings.ws_position_silence_seconds' in source
    assert 'settings.position_fallback_interval_seconds' in source
