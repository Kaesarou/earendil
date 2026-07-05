from app.brokers.etoro.payload_collections import keep_dict_items


def test_keep_dict_items_filters_non_dict_values():
    assert keep_dict_items(
        [
            {'id': 1},
            'ignored',
            123,
            {'id': 2},
            None,
        ]
    ) == [
        {'id': 1},
        {'id': 2},
    ]


def test_keep_dict_items_returns_empty_list_when_no_dict_values():
    assert keep_dict_items(['ignored', 123, None]) == []
