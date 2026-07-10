from app.risk.position_sizing import constant_risk_position_value
from app.risk.structural_stop import calculate_structural_stop


def test_buy_structural_stop_uses_invalidation_spread_atr_and_minimum():
    result = calculate_structural_stop(
        side='BUY',
        entry_price=100,
        invalidation_price=99.5,
        atr_percent=0.4,
        atr_multiplier=2,
        minimum_distance_percent=0.4,
        spread_percent=0.1,
    )
    assert result.valid
    assert result.structural_distance_percent == 0.6
    assert result.effective_distance_percent == 0.8


def test_sell_structural_stop_is_symmetric():
    result = calculate_structural_stop(
        side='SELL',
        entry_price=100,
        invalidation_price=100.7,
        atr_percent=0.2,
        atr_multiplier=1,
        minimum_distance_percent=0.4,
        spread_percent=0.1,
    )
    assert result.valid
    assert round(result.effective_distance_percent, 4) == 0.8


def test_invalid_directional_invalidation_is_rejected():
    result = calculate_structural_stop(
        side='BUY',
        entry_price=100,
        invalidation_price=101,
        atr_percent=0.2,
        atr_multiplier=1,
        minimum_distance_percent=0.4,
        spread_percent=0.1,
    )
    assert not result.valid


def test_position_size_reduces_to_keep_risk_constant():
    assert constant_risk_position_value(
        baseline_position_value=1000,
        baseline_stop_loss_percent=0.5,
        effective_stop_loss_percent=1.0,
    ) == 500
