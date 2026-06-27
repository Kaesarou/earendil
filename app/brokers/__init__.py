from app.brokers.cached_broker import CachedBrokerClient


_original_load_market_snapshots = CachedBrokerClient._load_market_snapshots


def _load_market_snapshots_without_etoro_batch(
    self: CachedBrokerClient,
    symbols: list[str],
):
    if self._looks_like_etoro_delegate():
        return {
            symbol: self.delegate.get_market_snapshot(symbol)
            for symbol in symbols
        }

    return _original_load_market_snapshots(self, symbols)


CachedBrokerClient._load_market_snapshots = _load_market_snapshots_without_etoro_batch
