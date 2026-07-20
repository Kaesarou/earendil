from app.runtime.market_data_maintenance import MarketDataMaintenance


class RuntimeState(MarketDataMaintenance):
    def __init__(self) -> None:
        self.active_symbols = ['AIR.PA', 'AAPL']
        self.context_asset_classes = {'FRA40': object(), 'SPX500': object()}
        self._applied_feed_symbols = ('AIR.PA', 'FRA40')

    def _desired_market_data_symbols(self) -> list[str]:
        return [
            *self.active_symbols,
            *self.context_asset_classes,
        ]


def test_rest_fallback_only_considers_applied_subscriptions():
    runtime = RuntimeState()

    assert runtime._applied_monitored_symbols() == ['AIR.PA', 'FRA40']
