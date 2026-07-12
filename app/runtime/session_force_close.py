import logging

from app.execution.position_tracker import PositionCloseSignal, PositionTracker
from app.execution.trade_executor import TradeExecutor
from app.journal.jsonl_journal import JsonlJournal
from app.market.models import MarketSnapshot
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.risk_manager import RiskManager
from app.runtime.position_lifecycle import (
    BrokerAuthorizationErrorChecker,
    register_trade_cooldown_for_closed_position,
)
from app.runtime.trading_session_window import (
    FORCE_CLOSE_BEFORE_SESSION_END,
    TradingSessionDecision,
)

logger = logging.getLogger(__name__)


def force_close_positions_before_session_end(
    *,
    symbol: str,
    snapshot: MarketSnapshot,
    session_decision: TradingSessionDecision,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    trade_journal: JsonlJournal,
    is_broker_authorization_error: BrokerAuthorizationErrorChecker,
    position_store: PositionStore | None = None,
    cooldown_store: TradeCooldownStore | None = None,
) -> None:
    if not session_decision.force_close_required:
        return

    for position in position_tracker.open_positions_snapshot():
        if position.symbol != symbol:
            continue

        close_signal = PositionCloseSignal(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            exit_price=snapshot.last,
            reason=FORCE_CLOSE_BEFORE_SESSION_END,
            detected_at=snapshot.timestamp,
            metadata={
                'session_decision': session_decision.reason,
                'time_until_session_end_minutes': (
                    session_decision.time_until_session_end_minutes
                ),
            },
        )

        try:
            executor.close(close_signal.position_id)
            closed_position = position_tracker.record_closed_position(close_signal)
            closed_session_key = risk_manager.record_close_position(close_signal.symbol)

            if position_store is not None:
                position_store.delete_open_position(close_signal.position_id)

            if cooldown_store is not None:
                register_trade_cooldown_for_closed_position(
                    closed_position=closed_position,
                    risk_manager=risk_manager,
                    cooldown_store=cooldown_store,
                    trade_journal=trade_journal,
                    session_key=closed_session_key,
                )

            trade_journal.write(
                'position_closed',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'closed_position': closed_position,
                    'session_decision': session_decision,
                },
            )
            logger.info(
                'Position force-closed before session end | symbol=%s | '
                'position_id=%s',
                symbol,
                close_signal.position_id,
            )

        except Exception as exc:
            if is_broker_authorization_error(exc):
                raise
            logger.exception(
                'Session force close error | symbol=%s | position_id=%s | error=%s',
                symbol,
                close_signal.position_id,
                exc,
            )
            trade_journal.write(
                'position_close_error',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'message': str(exc),
                    'session_decision': session_decision,
                },
            )
