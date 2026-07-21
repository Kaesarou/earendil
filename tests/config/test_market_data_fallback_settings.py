import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.runtime.runtime_policy import (
    POSITION_FALLBACK_INTERVAL_SECONDS,
    WS_POSITION_SILENCE_SECONDS,
)


def test_position_fallback_policy_is_code_versioned():
    assert WS_POSITION_SILENCE_SECONDS == 15.0
    assert POSITION_FALLBACK_INTERVAL_SECONDS == 10.0


@pytest.mark.parametrize(
    'environment_name',
    [
        'WS_SYMBOL_SILENCE_SECONDS',
        'REST_FALLBACK_COOLDOWN_SECONDS',
        'WS_POSITION_SILENCE_SECONDS',
        'POSITION_FALLBACK_INTERVAL_SECONDS',
    ],
)
def test_environment_cannot_override_runtime_safety_policy(environment_name):
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        Settings(**{environment_name: 30})
