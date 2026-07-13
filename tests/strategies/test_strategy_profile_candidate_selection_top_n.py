import pytest

from app.instruments.models import AssetClass
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_strategy_profile_resolves_candidate_selection_config_for_every_asset_class():
    profile = BalancedStrategyConfig(
        candidate_selection_top_n=3,
        candidate_selection_min_score=115.0,
    )

    crypto_config = profile.candidate_selection_config_for_asset_class(AssetClass.CRYPTO)
    equity_us_config = profile.candidate_selection_config_for_asset_class(AssetClass.EQUITY_US)
    equity_eu_config = profile.candidate_selection_config_for_asset_class(AssetClass.EQUITY_EU)

    assert profile.candidate_selection_top_n == 3
    assert profile.candidate_selection_min_score == 115.0
    assert crypto_config.top_n == 3
    assert crypto_config.min_score == 115.0
    assert equity_us_config.top_n == 3
    assert equity_us_config.min_score == 115.0
    assert equity_eu_config.top_n == 3
    assert equity_eu_config.min_score == 115.0


def test_strategy_profile_rejects_invalid_asset_class():
    profile = BalancedStrategyConfig()

    with pytest.raises(ValueError, match='Unsupported asset class'):
        profile.instrument_config_for_asset_class('BROKEN')
