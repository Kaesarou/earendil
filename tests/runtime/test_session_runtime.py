from datetime import datetime, timezone

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass
from app.runtime.session_runtime import filter_symbols_by_trading_session
from app.runtime.trading_session_window import (
    AssetTradingSessionConfig,
    TradingSessionService,
    TradingSessionState,
    parse_trading_sessions,
)


def test_filter_symbols_by_trading_session_keeps_only_active_symbols():
    settings = Settings(
        EQUITY_US_SYMBOLS='AAPL',
        EQUITY_EU_SYMBOLS='AIR.PA',
    )
    registry = InstrumentRegistry(settings)
    service = TradingSessionService(
        configs={
            AssetClass.EQUITY_US: AssetTradingSessionConfig(
                asset_class=AssetClass.EQUITY_US,
                sessions=parse_trading_sessions('15:00-22:00'),
            ),
            AssetClass.EQUITY_EU: AssetTradingSessionConfig(
                asset_class=AssetClass.EQUITY_EU,
                sessions=parse_trading_sessions('09:00-12:00'),
            ),
            AssetClass.CRYPTO: AssetTradingSessionConfig(
                asset_class=AssetClass.CRYPTO,
                sessions=(),
            ),
        },
        timezone_name='Europe/Paris',
    )

    symbols_to_fetch, decisions, _ = filter_symbols_by_trading_session(
        symbols=['AAPL', 'AIR.PA'],
        instrument_registry=registry,
        trading_session_service=service,
        trading_session_state=TradingSessionState(),
        now=datetime(2026, 7, 5, 14, 0, tzinfo=timezone.utc),
    )

    assert symbols_to_fetch == ['AAPL']
    assert decisions['AAPL'].collect_snapshots
    assert not decisions['AIR.PA'].collect_snapshots
