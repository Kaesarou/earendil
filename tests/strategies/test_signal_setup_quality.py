from app.strategies.signals import Signal


def test_signal_exposes_setup_quality() -> None:
    signal = Signal(action='BUY', setup_quality=0.8, reason='trend_bullish_breakout')

    assert signal.setup_quality == 0.8


def test_hold_signal_has_no_setup_quality() -> None:
    signal = Signal.hold('no_signal')

    assert signal.setup_quality == 0.0
