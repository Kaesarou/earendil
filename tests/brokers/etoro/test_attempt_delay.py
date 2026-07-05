from app.brokers.etoro.attempt_delay import delay_seconds_for_attempt


def test_delay_seconds_for_attempt_matches_attempt_number():
    assert delay_seconds_for_attempt(1) == 1
    assert delay_seconds_for_attempt(2) == 2
    assert delay_seconds_for_attempt(3) == 3
