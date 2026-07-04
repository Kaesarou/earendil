import pytest

from app.brokers.etoro.position_instrument_cache import (
    cached_position_instrument_id,
    forget_position_instrument_id,
    remember_position_instrument_id,
    require_position_instrument_id,
)


def test_remember_position_instrument_id_stores_mapping():
    position_instruments = {}

    remember_position_instrument_id(
        position_instruments=position_instruments,
        position_id='position-1',
        instrument_id=100000,
    )

    assert position_instruments == {'position-1': 100000}


def test_cached_position_instrument_id_returns_stored_instrument_id():
    assert cached_position_instrument_id(
        position_instruments={'position-1': 100000},
        position_id='position-1',
    ) == 100000


def test_cached_position_instrument_id_returns_none_when_missing():
    assert cached_position_instrument_id(
        position_instruments={},
        position_id='position-1',
    ) is None


def test_forget_position_instrument_id_removes_mapping():
    position_instruments = {'position-1': 100000}

    forget_position_instrument_id(
        position_instruments=position_instruments,
        position_id='position-1',
    )

    assert position_instruments == {}


def test_forget_position_instrument_id_is_idempotent_when_missing():
    position_instruments = {}

    forget_position_instrument_id(
        position_instruments=position_instruments,
        position_id='position-1',
    )

    assert position_instruments == {}


def test_require_position_instrument_id_returns_stored_instrument_id():
    assert require_position_instrument_id(
        position_instruments={'position-1': 100000},
        position_id='position-1',
    ) == 100000


def test_require_position_instrument_id_raises_when_missing():
    with pytest.raises(ValueError, match='Cannot close eToro position without known instrument id'):
        require_position_instrument_id(
            position_instruments={},
            position_id='position-1',
        )
