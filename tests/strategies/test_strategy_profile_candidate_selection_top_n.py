import pytest

from app.instruments.models import AssetClass
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_strategy_profile_resolves_asset_specific_selection_configs():
    profile = BalancedStrategyConfig()
    crypto = profile.candidate_selection_config_for_asset_class(AssetClass.CRYPTO)
    us = profile.candidate_selection_config_for_asset_class(AssetClass.EQUITY_US)
    eu = profile.candidate_selection_config_for_asset_class(AssetClass.EQUITY_EU)

    assert (crypto.top_n, crypto.min_score) == (2, 115.0)
    assert (us.top_n, us.min_score) == (2, 115.0)
    assert (eu.top_n, eu.min_score) == (1, 110.0)
    assert not hasattr(us, 'dynamic_min_score')


def test_strategy_profile_rejects_invalid_asset_class():
    with pytest.raises(ValueError, match='Unsupported asset class'):
        BalancedStrategyConfig().instrument_config_for_asset_class('BROKEN')
