from app.instruments.models import AssetClass
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_equity_profiles_use_dynamic_equity_trade_costs():
    profiles = BalancedStrategyConfig().risk_profiles()
    trade_cost = profiles[AssetClass.EQUITY_US].trade_cost

    assert trade_cost.open_fee_percent == 0.15
    assert trade_cost.close_fee_percent == 0.15
    assert trade_cost.include_spread_cost
    assert trade_cost.min_expected_net_profit_percent == 0.10


def test_crypto_profile_uses_dynamic_crypto_trade_costs():
    profiles = BalancedStrategyConfig().risk_profiles()
    trade_cost = profiles[AssetClass.CRYPTO].trade_cost

    assert trade_cost.open_fee_percent == 1.0
    assert trade_cost.close_fee_percent == 1.0
    assert trade_cost.include_spread_cost
    assert trade_cost.min_expected_net_profit_percent == 0.10
