from app.market.models import MarketSnapshot
from app.strategies.breakout import BreakoutStrategy


def test_breakout_strategy_emits_buy_signal_after_breakout():
    strategy = BreakoutStrategy(lookback=3, min_breakout_percent=0.01)
    prices = [100, 101, 102, 103]

    signal = None
    for price in prices:
        signal = strategy.on_snapshot(MarketSnapshot.now('BTC', price, price, price))

    assert signal is not None
    assert signal.action == 'BUY'
