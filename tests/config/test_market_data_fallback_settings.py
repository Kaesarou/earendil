from app.config.settings import Settings


def test_position_fallback_defaults_are_conservative():
    settings = Settings()

    assert settings.ws_position_silence_seconds == 15.0
    assert settings.position_fallback_interval_seconds == 10.0


def test_legacy_environment_names_are_accepted_but_not_allowed_below_floors():
    settings = Settings(
        WS_SYMBOL_SILENCE_SECONDS=5,
        REST_FALLBACK_COOLDOWN_SECONDS=5,
    )

    assert settings.ws_position_silence_seconds == 15.0
    assert settings.position_fallback_interval_seconds == 10.0


def test_new_environment_names_can_raise_the_thresholds():
    settings = Settings(
        WS_POSITION_SILENCE_SECONDS=30,
        POSITION_FALLBACK_INTERVAL_SECONDS=20,
    )

    assert settings.ws_position_silence_seconds == 30.0
    assert settings.position_fallback_interval_seconds == 20.0
