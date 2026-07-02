from app.instruments.models import AssetClass
from app.strategies.balanced_strategy import BalancedStrategyConfig


def test_strategy_profile_resolves_global_pre_scan_top_n_for_every_asset_class():
    profile = BalancedStrategyConfig(pre_scan_top_n=3)

    crypto_config = profile.pre_scan_config_for_asset_class(AssetClass.CRYPTO)
    equity_us_config = profile.pre_scan_config_for_asset_class(AssetClass.EQUITY_US)
    equity_eu_config = profile.pre_scan_config_for_asset_class(AssetClass.EQUITY_EU)

    assert profile.pre_scan_top_n == 3
    assert crypto_config.top_n == 3
    assert equity_us_config.top_n == 3
    assert equity_eu_config.top_n == 3
