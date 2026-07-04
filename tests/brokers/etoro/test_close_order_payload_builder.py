from app.brokers.etoro.close_order_payload_builder import build_close_order_payload


def test_build_close_order_payload():
    assert build_close_order_payload(100000) == {
        'InstrumentId': 100000,
        'UnitsToDeduct': None,
    }
