import pytest

from app.brokers.etoro.scalar_extractors import (
    extract_float,
    extract_int,
    extract_optional_float,
    extract_optional_int,
)


def test_extract_optional_float_returns_first_matching_value():
    assert extract_optional_float({'Bid': '10.5', 'bid': '11.5'}, ('Bid', 'bid')) == 10.5


def test_extract_optional_float_accepts_zero_value():
    assert extract_optional_float({'Bid': 0}, ('Bid',)) == 0.0
    assert extract_optional_float({'Bid': '0'}, ('Bid',)) == 0.0


def test_extract_optional_float_returns_none_when_missing():
    assert extract_optional_float({}, ('Bid', 'bid')) is None


def test_extract_float_returns_required_value():
    assert extract_float({'Ask': '12.25'}, ('Ask', 'ask')) == 12.25


def test_extract_float_raises_when_missing():
    with pytest.raises(ValueError, match='Unable to extract required float'):
        extract_float({}, ('Ask', 'ask'))


def test_extract_optional_int_returns_first_matching_value():
    assert extract_optional_int({'instrumentID': '1001', 'instrumentId': '1002'}, ('instrumentID', 'instrumentId')) == 1001


def test_extract_optional_int_accepts_zero_value():
    assert extract_optional_int({'instrumentID': 0}, ('instrumentID',)) == 0
    assert extract_optional_int({'instrumentID': '0'}, ('instrumentID',)) == 0


def test_extract_optional_int_returns_none_when_missing():
    assert extract_optional_int({}, ('instrumentID', 'instrumentId')) is None


def test_extract_int_returns_required_value():
    assert extract_int({'instrumentId': '1002'}, ('instrumentID', 'instrumentId')) == 1002


def test_extract_int_raises_when_missing():
    with pytest.raises(ValueError, match='Unable to extract required int'):
        extract_int({}, ('instrumentID', 'instrumentId'))
