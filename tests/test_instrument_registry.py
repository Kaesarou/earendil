from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass


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
    assert registry.resolve('UNKNOWN').asset_class == AssetClass.UNKNOWN


def test_instrument_registry_returns_crypto_risk_profile():
    settings = Settings(
        CRYPTO_SYMBOLS='DOGE',
        CRYPTO_STOP_LOSS_PERCENT=1.5,
        CRYPTO_TAKE_PROFIT_PERCENT=3.0,
        CRYPTO_MIN_EXPECTED_NET_PROFIT=8.0,
        CRYPTO_ESTIMATED_ROUND_TRIP_FEES=3.0,
        CRYPTO_FORCE_CLOSE_ENABLED=False,
    )
    registry = InstrumentRegistry(settings)

    risk_profile = registry.risk_profile_for('DOGE')

    assert risk_profile.asset_class == AssetClass.CRYPTO
    assert risk_profile.stop_loss_percent == 1.5
    assert risk_profile.take_profit_percent == 3.0
    assert risk_profile.min_expected_net_profit == 8.0
    assert risk_profile.estimated_round_trip_fees == 3.0
    assert risk_profile.force_close_enabled is False


def test_instrument_registry_falls_back_to_global_settings_for_unknown_asset_class():
    settings = Settings(
        MAX_POSITION_SIZE_PERCENT=40.0,
        STOP_LOSS_PERCENT=0.3,
        TAKE_PROFIT_PERCENT=0.5,
        ESTIMATED_ROUND_TRIP_FEES=0.25,
        MIN_EXPECTED_NET_PROFIT=0.15,
        FORCE_CLOSE_HOUR=23,
        FORCE_CLOSE_MINUTE=59,
    )
    registry = InstrumentRegistry(settings)

    risk_profile = registry.risk_profile_for('AAPL')

    assert risk_profile.asset_class == AssetClass.UNKNOWN
    assert risk_profile.max_position_size_percent == 40.0
    assert risk_profile.stop_loss_percent == 0.3
    assert risk_profile.take_profit_percent == 0.5
    assert risk_profile.estimated_round_trip_fees == 0.25
    assert risk_profile.min_expected_net_profit == 0.15
    assert risk_profile.force_close_enabled is True
    assert risk_profile.force_close_hour == 23
    assert risk_profile.force_close_minute == 59
