def build_close_order_payload(instrument_id: int) -> dict:
    return {
        'InstrumentId': instrument_id,
        'UnitsToDeduct': None,
    }
