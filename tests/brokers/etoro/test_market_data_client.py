from app.brokers.etoro.market_data_client import EtoroRestMarketDataClient


def _build_client(cache_path) -> EtoroRestMarketDataClient:
    client = EtoroRestMarketDataClient(
        api_key='api-key',
        user_key='user-key',
        instrument_id_cache_path=str(cache_path),
    )
    client.resolution_min_interval_seconds = 0.0
    return client


def test_instrument_ids_are_persisted_and_reused(tmp_path, monkeypatch):
    cache_path = tmp_path / 'instrument_ids.json'
    first = _build_client(cache_path)
    searches: list[str] = []

    def fake_get(path: str, params=None):
        symbol = params['internalSymbolFull']
        searches.append(symbol)
        return {
            'items': [
                {
                    'internalSymbolFull': symbol,
                    'internalInstrumentId': {
                        'AIR.PA': 1234,
                        'FRA40': 31,
                    }[symbol],
                }
            ]
        }

    monkeypatch.setattr(first, '_get', fake_get)

    assert first.resolve_instrument_ids(['AIR.PA', 'FRA40']) == {
        'AIR.PA': 1234,
        'FRA40': 31,
    }
    assert searches == ['AIR.PA', 'FRA40']
    assert cache_path.is_file()

    second = _build_client(cache_path)
    monkeypatch.setattr(
        second,
        '_get',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('cached instruments must not be searched again')
        ),
    )

    assert second.resolve_instrument_ids(['AIR.PA', 'FRA40']) == {
        'AIR.PA': 1234,
        'FRA40': 31,
    }
    assert second.symbol_by_instrument_id == {
        1234: 'AIR.PA',
        31: 'FRA40',
    }
