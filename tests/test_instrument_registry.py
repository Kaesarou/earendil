import pytest

from app.config.settings import Settings
from app.instruments.base_configs import CRYPTO_CONFIG
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile


def test_instrument_registry_resolves_asset_classes_from_settings():
    settings = Settings(
        CRYPTO_SYMBOLS='BTC,ETH,DOGE,SOL',
        EQUITY_US_SYMBOLS='MSFT,NVDA,AAPL',
        EQUITY_EU_SYMBOLS='AIR.PA,SAF.PA',
    )
    registry = InstrumentRegistry(settings)

    assert registry.resolve('doge').asset_class == AssetClass.CRYPTO
    assert registry.resolve('MSFT').asset_class == AssetClass.EQUITY_US
    assert registry.resolve('air.pa').asset_class == AssetClass.EQUITY_EU


def test_instrument_registry_rejects_unsupported_symbol():
    settings = Settings(
        CRYPTO_SYMBOLS='BTC',
        EQUITY_US_SYMBOLS='AAPL',
        EQUITY_EU_SYMBOLS='AIR.PA',
    )
    registry = InstrumentRegistry(settings)

    with pytest.raises(ValueError, match='Unsupported instrument symbol'):
        registry.resolve('MSFT')


def test_instrument_registry_rejects_ambiguous_symbol():
    settings = Settings(
        CRYPTO_SYMBOLS='AAPL',
        EQUITY_US_SYMBOLS='AAPL',
        EQUITY_EU_SYMBOLS='',
    )
    registry = InstrumentRegistry(settings)

    with pytest.raises(ValueError, match='Ambiguous instrument symbol'):
        registry.resolve('AAPL')


def test_instrument_registry_rejects_unsupported_watchlist_symbols():
    settings = Settings(
        WATCHLIST='AAPL,MSFT,DOGE',
        CRYPTO_SYMBOLS='DOGE',
        EQUITY_US_SYMBOLS='AAPL',
        EQUITY_EU_SYMBOLS='',
    )
    registry = InstrumentRegistry(settings)

    with pytest.raises(ValueError) as exc_info:
        registry.validate_supported_symbols(settings.watchlist_symbols())

    message = str(exc_info.value)
    assert 'MSFT' in message
    assert 'WATCHLIST' in message
    assert 'CRYPTO_SYMBOLS' in message
    assert 'EQUITY_US_SYMBOLS' in message
    assert 'EQUITY_EU_SYMBOLS' in message


def test_instrument_registry_accepts_supported_watchlist_symbols():
    settings = Settings(
        WATCHLIST='AAPL,DOGE,AIR.PA',
        CRYPTO_SYMBOLS='DOGE',
        EQUITY_US_SYMBOLS='AAPL',
        EQUITY_EU_SYMBOLS='AIR.PA',
    )
    registry = InstrumentRegistry(settings)

    registry.validate_supported_symbols(settings.watchlist_symbols())


def test_instrument_registry_returns_default_crypto_config_and_risk_profile():
    settings = Settings(CRYPTO_SYMBOLS='DOGE')
    registry = InstrumentRegistry(settings)

    instrument_config = registry.config_for('DOGE')
    risk_profile = registry.risk_profile_for('DOGE')

    assert instrument_config == CRYPTO_CONFIG
    assert risk_profile == instrument_config.risk
    assert risk_profile.asset_class == AssetClass.CRYPTO
    assert risk_profile.stop_loss_percent == 1.5
    assert risk_profile.take_profit_percent == 3.0
    assert risk_profile.force_close_enabled is False


def test_instrument_registry_can_receive_custom_risk_profiles_for_tests_or_future_profiles():
    settings = Settings(CRYPTO_SYMBOLS='DOGE')
    custom_crypto_profile = RiskProfile(
        asset_class=AssetClass.CRYPTO,
        max_position_size_percent=1.0,
        stop_loss_percent=2.0,
        take_profit_percent=4.0,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=0.20,
        min_move_spread_ratio=4.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.8,
        max_stop_loss_percent=2.5,
        min_take_profit_percent=1.5,
        max_take_profit_percent=5.0,
    )

    registry = InstrumentRegistry(
        settings,
        risk_profiles={
            AssetClass.CRYPTO: custom_crypto_profile,
        },
    )

    instrument_config = registry.config_for('DOGE')
    risk_profile = registry.risk_profile_for('DOGE')

    assert instrument_config.risk == custom_crypto_profile
    assert risk_profile.asset_class == AssetClass.CRYPTO
    assert risk_profile.max_position_size_percent == 1.0
    assert risk_profile.stop_loss_percent == 2.0
    assert risk_profile.take_profit_percent == 4.0
