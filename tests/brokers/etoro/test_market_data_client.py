from app.brokers.etoro.market_data_client import EtoroRestMarketDataClient


class FakeEtoroClient:
    def __init__(self) -> None:
        self.instrument_ids_by_symbol: dict[str, int] = {}
        self.symbol_by_instrument_id: dict[int, str] = {}
        self.searches: list[str] = []

    def _find_instrument_id(self, symbol: str) -> int:
        self.searches.append(symbol)
        instrument_id = {'AIR.PA': 1234, 'FRA40': 31}[symbol]
        self.instrument_ids_by_symbol[symbol] = instrument_id
        self.symbol_by_instrument_id[instrument_id] = symbol
        return instrument_id

    def get_market_snapshots(self, symbols):
        raise NotImplementedError


def test_instrument_ids_are_persisted_and_reused(tmp_path):
    cache_path = tmp_path / 'instrument_ids.json'
    first_client = FakeEtoroClient()
    first = EtoroRestMarketDataClient(
        first_client,
        instrument_id_cache_path=str(cache_path),
        resolution_min_interval_seconds=0.0,
    )

    assert first.resolve_instrument_ids(['AIR.PA', 'FRA40']) == {
        'AIR.PA': 1234,
        'FRA40': 31,
    }
    assert first_client.searches == ['AIR.PA', 'FRA40']
    assert cache_path.is_file()

    second_client = FakeEtoroClient()
    second = EtoroRestMarketDataClient(
        second_client,
        instrument_id_cache_path=str(cache_path),
        resolution_min_interval_seconds=0.0,
    )

    assert second.resolve_instrument_ids(['AIR.PA', 'FRA40']) == {
        'AIR.PA': 1234,
        'FRA40': 31,
    }
    assert second_client.searches == []
    assert second_client.symbol_by_instrument_id == {
        1234: 'AIR.PA',
        31: 'FRA40',
    }
