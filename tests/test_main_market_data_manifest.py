from app.config.settings import Settings
from app.main import build_market_data_manifest


def test_market_data_manifest_uses_position_fallback_settings():
    settings = Settings.model_construct(
        market_data_mode='auto',
        market_data_queue_capacity=4096,
        ws_position_silence_seconds=15.0,
        ws_global_silence_seconds=15.0,
        rest_control_interval_seconds=60.0,
        position_fallback_interval_seconds=10.0,
        decision_window_grace_seconds=5.0,
    )

    manifest = build_market_data_manifest(settings)

    assert manifest == {
        'mode': 'auto',
        'queue_capacity': 4096,
        'position_silence_seconds': 15.0,
        'global_silence_seconds': 15.0,
        'rest_control_interval_seconds': 60.0,
        'position_fallback_interval_seconds': 10.0,
        'decision_window_grace_seconds': 5.0,
    }
    assert 'symbol_silence_seconds' not in manifest
    assert 'fallback_cooldown_seconds' not in manifest
