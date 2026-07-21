from app.main import build_market_data_manifest
from app.runtime.runtime_policy import (
    CANDLE_CLOCK_GRACE_SECONDS,
    CANDLE_MAX_CARRY_FORWARD_AGE_SECONDS,
    CANDLE_ORDERING_DROP_DEGRADE_COUNT,
    CANDLE_ORDERING_DROP_DEGRADE_RATIO,
    DECISION_WINDOW_GRACE_SECONDS,
    ETORO_INSTRUMENT_RESOLUTION_MIN_INTERVAL_SECONDS,
    MARKET_DATA_QUEUE_CAPACITY,
    POSITION_FALLBACK_INTERVAL_SECONDS,
    POSITION_RECONCILIATION_GRACE_SECONDS,
    POSITION_RECONCILIATION_MISS_INTERVAL_SECONDS,
    POSITION_RECONCILIATION_REQUIRED_MISSES,
    REST_CONTROL_ANOMALY_PERCENT,
    REST_CONTROL_INTERVAL_SECONDS,
    UNKNOWN_ORDER_LOOKUP_INTERVAL_SECONDS,
    UNKNOWN_ORDER_MAX_AGE_MINUTES,
    WS_GLOBAL_SILENCE_SECONDS,
    WS_POSITION_SILENCE_SECONDS,
)


def test_market_data_manifest_records_code_versioned_runtime_policy():
    manifest = build_market_data_manifest()

    assert manifest == {
        'mode': 'websocket',
        'queue_capacity': MARKET_DATA_QUEUE_CAPACITY,
        'position_silence_seconds': WS_POSITION_SILENCE_SECONDS,
        'global_silence_seconds': WS_GLOBAL_SILENCE_SECONDS,
        'rest_control_interval_seconds': REST_CONTROL_INTERVAL_SECONDS,
        'rest_control_anomaly_percent': REST_CONTROL_ANOMALY_PERCENT,
        'position_fallback_interval_seconds': (
            POSITION_FALLBACK_INTERVAL_SECONDS
        ),
        'decision_window_grace_seconds': DECISION_WINDOW_GRACE_SECONDS,
        'candle_clock_grace_seconds': CANDLE_CLOCK_GRACE_SECONDS,
        'candle_max_carry_forward_age_seconds': (
            CANDLE_MAX_CARRY_FORWARD_AGE_SECONDS
        ),
        'candle_ordering_drop_degrade_count': (
            CANDLE_ORDERING_DROP_DEGRADE_COUNT
        ),
        'candle_ordering_drop_degrade_ratio': (
            CANDLE_ORDERING_DROP_DEGRADE_RATIO
        ),
        'position_reconciliation_grace_seconds': (
            POSITION_RECONCILIATION_GRACE_SECONDS
        ),
        'position_reconciliation_required_misses': (
            POSITION_RECONCILIATION_REQUIRED_MISSES
        ),
        'position_reconciliation_miss_interval_seconds': (
            POSITION_RECONCILIATION_MISS_INTERVAL_SECONDS
        ),
        'unknown_order_lookup_interval_seconds': (
            UNKNOWN_ORDER_LOOKUP_INTERVAL_SECONDS
        ),
        'unknown_order_max_age_minutes': UNKNOWN_ORDER_MAX_AGE_MINUTES,
        'instrument_resolution_min_interval_seconds': (
            ETORO_INSTRUMENT_RESOLUTION_MIN_INTERVAL_SECONDS
        ),
        'sellshort_safety_sl_buffer_percent': 0.30,
    }
