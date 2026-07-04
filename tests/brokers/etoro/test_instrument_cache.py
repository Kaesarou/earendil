from app.brokers.etoro.instrument_cache import (
    cached_instrument_id,
    normalized_symbol,
    remember_instrument_id,
)


def test_normalized_symbol_uppercases_symbol():
    assert normalized_symbol('abc') == 'ABC'
    assert normalized_symbol('AbC') == 'ABC'


def test_cached_instrument_id_reads_normalized_symbol():
    instrument_ids_by_symbol = {
        'ABC': 100000,
    }

    assert cached_instrument_id(
        instrument_ids_by_symbol=instrument_ids_by_symbol,
        symbol='abc',
    ) == 100000


def test_cached_instrument_id_returns_none_when_missing():
    assert cached_instrument_id(
        instrument_ids_by_symbol={},
        symbol='abc',
    ) is None


def test_remember_instrument_id_updates_both_cache_dictionaries():
    instrument_ids_by_symbol = {}
    symbol_by_instrument_id = {}

    remember_instrument_id(
        instrument_ids_by_symbol=instrument_ids_by_symbol,
        symbol_by_instrument_id=symbol_by_instrument_id,
        symbol='abc',
        instrument_id=100000,
    )

    assert instrument_ids_by_symbol == {'ABC': 100000}
    assert symbol_by_instrument_id == {100000: 'ABC'}
