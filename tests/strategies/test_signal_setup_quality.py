from app.strategies.signals import Signal


def test_signal_setup_quality_is_confidence_compatibility_alias() -> None:
    signal = Signal(action='BUY', confidence=0.8, reason='trend_bullish_breakout')

    assert signal.setup_quality == 0.8
    assert signal.confidence == signal.setup_quality


def test_hold_signal_has_no_setup_quality() -> None:
    signal = Signal.hold('no_signal')

    assert signal.setup_quality == 0.0
    assert signal.confidence == 0.0
