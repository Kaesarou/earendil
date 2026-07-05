from datetime import datetime

from app.instruments.instrument_registry import InstrumentRegistry
from app.runtime.trading_session_window import TradingSessionService, TradingSessionState


def filter_symbols_by_trading_session(
    *,
    symbols: list[str],
    instrument_registry: InstrumentRegistry,
    trading_session_service: TradingSessionService,
    trading_session_state: TradingSessionState,
    now: datetime,
):
    symbols_to_fetch: list[str] = []
    session_decisions = {}
    started_session_symbols: list[str] = []
    closed_session_keys: set[str] = set()

    for symbol in symbols:
        asset_class = instrument_registry.resolve(symbol).asset_class
        decision = trading_session_service.evaluate(asset_class=asset_class, now=now)
        session_decisions[symbol] = decision

        started, closed_session_key = trading_session_state.mark_and_detect_transition(
            symbol=symbol,
            decision=decision,
        )
        if started:
            started_session_symbols.append(symbol)
        if closed_session_key is not None:
            closed_session_keys.add(closed_session_key)

        if decision.collect_snapshots:
            symbols_to_fetch.append(symbol)

    return symbols_to_fetch, session_decisions, started_session_symbols, closed_session_keys
