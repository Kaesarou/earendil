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
    registry = InstrumentRegistry(Settings(CRYPTO_SYMBOLS='BTC', EQUITY_US_SYMBOLS='AAPL', EQUITY_EU_SYMBOLS='AIR.PA'))
    with pytest.raises(ValueError, match='Unsupported instrument symbol'):
        registry.resolve('MSFT')


def test_instrument_registry_rejects_ambiguous_symbol():
    registry = InstrumentRegistry(Settings(CRYPTO_SYMBOLS='AAPL', EQUITY_US_SYMBOLS='AAPL'))
    with pytest.raises(ValueError, match='Ambiguous instrument symbol'):
        registry.resolve('AAPL')


def test_instrument_registry_rejects_unsupported_watchlist_symbols():
    settings = Settings(WATCHLIST='AAPL,MSFT,DOGE', CRYPTO_SYMBOLS='DOGE', EQUITY_US_SYMBOLS='AAPL')
    registry = InstrumentRegistry(settings)
    with pytest.raises(ValueError) as exc_info:
        registry.validate_supported_symbols(settings.watchlist_symbols())
    message = str(exc_info.value)
    assert 'MSFT' in message
    assert 'WATCHLIST' in message


def test_instrument_registry_accepts_supported_watchlist_symbols():
    settings = Settings(WATCHLIST='AAPL,DOGE,AIR.PA', CRYPTO_SYMBOLS='DOGE', EQUITY_US_SYMBOLS='AAPL', EQUITY_EU_SYMBOLS='AIR.PA')
    InstrumentRegistry(settings).validate_supported_symbols(settings.watchlist_symbols())


def test_instrument_registry_returns_default_crypto_fixed_profile():
    registry = InstrumentRegistry(Settings(CRYPTO_SYMBOLS='DOGE'))
    config = registry.config_for('DOGE')
    risk = registry.risk_profile_for('DOGE')
    assert config == CRYPTO_CONFIG
    assert risk == config.risk
    assert risk.asset_class == AssetClass.CRYPTO
    assert risk.profile_key == 'crypto_intraday_fixed_v1'
    assert risk.stop_loss_percent == 1.5
    assert risk.take_profit_percent == 3.0


def test_instrument_registry_accepts_custom_named_fixed_profile():
    settings = Settings(CRYPTO_SYMBOLS='DOGE')
    custom = RiskProfile(
        asset_class=AssetClass.CRYPTO,
        profile_key='crypto_custom_fixed_v1',
        max_position_size_percent=1.0,
        stop_loss_percent=2.0,
        take_profit_percent=4.0,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=0.20,
        min_move_spread_ratio=4.0,
    )
    registry = InstrumentRegistry(settings, risk_profiles={AssetClass.CRYPTO: custom})
    assert registry.config_for('DOGE').risk == custom
    assert registry.risk_profile_for('DOGE').profile_key == 'crypto_custom_fixed_v1'
