import pytest

from app.instruments.models import AssetClass
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_strategy_profile_resolves_asset_specific_selection_configs():
    profile = BalancedStrategyConfig()

    crypto = profile.candidate_selection_config_for_asset_class(
        AssetClass.CRYPTO
    )
    us = profile.candidate_selection_config_for_asset_class(
        AssetClass.EQUITY_US
    )
    eu = profile.candidate_selection_config_for_asset_class(
        AssetClass.EQUITY_EU
    )

    assert crypto.top_n == 2
    assert crypto.min_score == 115.0
    assert crypto.dynamic_min_score is None
    assert us.top_n == 2
    assert us.min_score == 115.0
    assert us.dynamic_min_score == 100.0
    assert eu.top_n == 1
    assert eu.min_score == 110.0
    assert eu.dynamic_min_score is None


def test_strategy_profile_rejects_invalid_asset_class():
    profile = BalancedStrategyConfig()

    with pytest.raises(ValueError, match='Unsupported asset class'):
        profile.instrument_config_for_asset_class('BROKEN')
