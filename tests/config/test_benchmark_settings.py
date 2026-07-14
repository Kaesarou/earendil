from app.config.settings import Settings
from app.instruments.models import AssetClass


def test_default_reference_indices_are_configured_by_asset_class():
    settings = Settings(
        WATCHLIST='BTC,AAPL,AIR.PA',
        CRYPTO_SYMBOLS='BTC',
        EQUITY_US_SYMBOLS='AAPL',
        EQUITY_EU_SYMBOLS='AIR.PA',
    )

    assert settings.benchmark_symbols_by_asset_class() == {
        AssetClass.CRYPTO: ('CRYPTO10',),
        AssetClass.EQUITY_US: ('SPX500',),
        AssetClass.EQUITY_EU: ('FRA40',),
    }


def test_reference_indices_can_be_explicitly_disabled():
    settings = Settings(
        WATCHLIST='AAPL',
        EQUITY_US_SYMBOLS='AAPL',
        MARKET_BENCHMARK_CRYPTO='',
        MARKET_BENCHMARK_EQUITY_US='',
        MARKET_BENCHMARK_EQUITY_EU='',
    )

    assert settings.benchmark_symbols_by_asset_class() == {
        AssetClass.CRYPTO: (),
        AssetClass.EQUITY_US: (),
        AssetClass.EQUITY_EU: (),
    }
