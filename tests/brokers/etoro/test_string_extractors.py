from app.brokers.etoro.string_extractors import extract_optional_string


def test_extract_optional_string_returns_first_present_value_as_string():
    assert extract_optional_string(
        {
            'secondary': 123,
            'primary': 456,
        },
        ('primary', 'secondary'),
    ) == '456'


def test_extract_optional_string_keeps_zero_values():
    assert extract_optional_string({'value': 0}, ('value',)) == '0'


def test_extract_optional_string_returns_none_when_missing():
    assert extract_optional_string({'unexpected': 'value'}, ('value',)) is None
