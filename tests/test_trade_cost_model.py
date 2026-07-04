from app.risk.trade_cost_model import TradeCostConfig, TradeCostModel


def test_trade_cost_model_estimates_crypto_costs():
    estimate = TradeCostModel().estimate(
        position_value=1000.0,
        expected_move_percent=3.0,
        spread_percent=None,
        config=TradeCostConfig(
            open_fee_percent=1.0,
            close_fee_percent=1.0,
            min_expected_net_profit_percent=0.10,
        ),
    )

    assert estimate.expected_gross_profit == 30.0
    assert estimate.open_fee == 10.0
    assert estimate.close_fee == 10.0
    assert estimate.spread_cost == 0.0
    assert estimate.total_estimated_cost == 20.0
    assert estimate.total_estimated_cost_percent == 2.0
    assert estimate.expected_net_profit == 10.0
    assert estimate.expected_net_profit_percent == 1.0
    assert estimate.min_expected_net_profit_percent == 0.10
    assert estimate.required_min_expected_net_profit_amount == 1.0


def test_trade_cost_model_estimates_equity_cfd_costs_with_spread():
    estimate = TradeCostModel().estimate(
        position_value=1000.0,
        expected_move_percent=1.6,
        spread_percent=0.10,
        config=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            include_spread_cost=True,
            min_expected_net_profit_percent=0.10,
        ),
    )

    assert estimate.expected_gross_profit == 16.0
    assert estimate.open_fee == 1.5
    assert estimate.close_fee == 1.5
    assert estimate.spread_cost == 1.0
    assert estimate.total_estimated_cost == 4.0
    assert estimate.total_estimated_cost_percent == 0.4
    assert estimate.expected_net_profit == 12.0
    assert estimate.expected_net_profit_percent == 1.2
    assert estimate.min_expected_net_profit_percent == 0.10
    assert estimate.required_min_expected_net_profit_amount == 1.0


def test_trade_cost_model_uses_fixed_fees_from_config():
    estimate = TradeCostModel().estimate(
        position_value=1000.0,
        expected_move_percent=1.6,
        spread_percent=0.10,
        config=TradeCostConfig(
            fixed_open_fee=1.0,
            fixed_close_fee=1.5,
            include_spread_cost=False,
            min_expected_net_profit_percent=0.10,
        ),
    )

    assert estimate.expected_gross_profit == 16.0
    assert estimate.open_fee == 0.0
    assert estimate.close_fee == 0.0
    assert estimate.fixed_fees == 2.5
    assert estimate.spread_cost == 0.0
    assert estimate.total_estimated_cost == 2.5
    assert estimate.total_estimated_cost_percent == 0.25
    assert estimate.expected_net_profit == 13.5
    assert estimate.expected_net_profit_percent == 1.35
    assert estimate.min_expected_net_profit_percent == 0.10
    assert estimate.required_min_expected_net_profit_amount == 1.0


def test_trade_cost_model_scales_required_min_profit_with_position_value():
    config = TradeCostConfig(
        open_fee_percent=1.0,
        close_fee_percent=1.0,
        min_expected_net_profit_percent=0.10,
    )

    small = TradeCostModel().estimate(
        position_value=500.0,
        expected_move_percent=3.0,
        spread_percent=None,
        config=config,
    )
    large = TradeCostModel().estimate(
        position_value=1000.0,
        expected_move_percent=3.0,
        spread_percent=None,
        config=config,
    )

    assert small.expected_net_profit_percent == large.expected_net_profit_percent
    assert small.required_min_expected_net_profit_amount == 0.5
    assert large.required_min_expected_net_profit_amount == 1.0
