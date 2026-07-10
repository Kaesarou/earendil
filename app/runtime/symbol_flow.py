import logging

from app.brokers.base import BrokerClient
from app.execution.candidate_ranking import build_trade_candidate
from app.execution.position_tracker import PositionTracker
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.journal.jsonl_journal import JsonlJournal
from app.market.candle_builder import CandleBuilder
from app.market.models import Candle, MarketSnapshot
from app.market.session_rules import TradingSessionDecision
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.models import TradePlan
from app.risk.risk_manager import RiskManager
from app.runtime.position_lifecycle import (
    BrokerAuthorizationErrorChecker,
    close_positions_triggered_by_snapshot,
)
from app.runtime.session_position_lifecycle import close_positions_before_session_end
from app.strategies.strategy import TrendStrategy

logger = logging.getLogger(__name__)


def process_symbol(
    symbol: str,
    broker: BrokerClient,
    strategy: TrendStrategy,
    risk_manager: RiskManager,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    candle_builder: CandleBuilder,
    trade_journal: JsonlJournal,
    market_journal: JsonlJournal,
    candle_journal: JsonlJournal,
    is_broker_authorization_error: BrokerAuthorizationErrorChecker,
    position_store: PositionStore | None = None,
    cooldown_store: TradeCooldownStore | None = None,
    snapshot: MarketSnapshot | None = None,
    session_decision: TradingSessionDecision | None = None,
    loop_id: int | None = None,
) -> TradeCandidate | None:
    snapshot = snapshot or broker.get_market_snapshot(symbol)
    market_journal.write(
        'market_snapshot',
        {'symbol': symbol, 'snapshot': snapshot, 'loop_id': loop_id},
    )
    strategy.on_snapshot(snapshot)

    close_positions_triggered_by_snapshot(
        symbol=symbol,
        snapshot=snapshot,
        executor=executor,
        position_tracker=position_tracker,
        risk_manager=risk_manager,
        trade_journal=trade_journal,
        position_store=position_store,
        cooldown_store=cooldown_store,
        is_broker_authorization_error=is_broker_authorization_error,
    )

    if session_decision is not None:
        close_positions_before_session_end(
            symbol=symbol,
            snapshot=snapshot,
            session_decision=session_decision,
            executor=executor,
            position_tracker=position_tracker,
            risk_manager=risk_manager,
            trade_journal=trade_journal,
            position_store=position_store,
            cooldown_store=cooldown_store,
            is_broker_authorization_error=is_broker_authorization_error,
        )

    closed_candle = candle_builder.on_snapshot(snapshot)
    if closed_candle is None:
        return None

    return process_closed_candle(
        symbol=symbol,
        snapshot=snapshot,
        closed_candle=closed_candle,
        strategy=strategy,
        risk_manager=risk_manager,
        trade_journal=trade_journal,
        candle_journal=candle_journal,
        session_decision=session_decision,
        loop_id=loop_id,
    )


def process_closed_candle(
    *,
    symbol: str,
    snapshot: MarketSnapshot,
    closed_candle: Candle,
    strategy: TrendStrategy,
    risk_manager: RiskManager,
    trade_journal: JsonlJournal,
    candle_journal: JsonlJournal,
    session_decision: TradingSessionDecision | None = None,
    loop_id: int | None = None,
) -> TradeCandidate | None:
    candle_journal.write(
        'candle_closed',
        {'symbol': symbol, 'candle': closed_candle, 'loop_id': loop_id},
    )

    signal = strategy.on_candle(closed_candle)
    if signal.action == 'HOLD':
        logger.debug(
            'Strategy hold | symbol=%s | reason=%s | candle_close=%s',
            symbol,
            signal.reason,
            closed_candle.close,
        )
        return _write_rejected_decision(
            symbol=symbol,
            snapshot=snapshot,
            closed_candle=closed_candle,
            signal=signal,
            reason=signal.reason,
            risk_manager=risk_manager,
            trade_journal=trade_journal,
            session_decision=session_decision,
            loop_id=loop_id,
        )

    logger.info(
        'Strategy candidate signal | symbol=%s | action=%s | setup_quality=%s | reason=%s | candle_close=%s',
        symbol,
        signal.action,
        signal.setup_quality,
        signal.reason,
        closed_candle.close,
    )

    if session_decision is None or session_decision.session_key is None:
        return _write_rejected_decision(
            symbol=symbol,
            snapshot=snapshot,
            closed_candle=closed_candle,
            signal=signal,
            reason='missing_trading_session',
            risk_manager=risk_manager,
            trade_journal=trade_journal,
            session_decision=session_decision,
            loop_id=loop_id,
        )

    if not session_decision.new_entries_allowed:
        return _write_rejected_decision(
            symbol=symbol,
            snapshot=snapshot,
            closed_candle=closed_candle,
            signal=signal,
            reason=session_decision.reason,
            risk_manager=risk_manager,
            trade_journal=trade_journal,
            session_decision=session_decision,
            loop_id=loop_id,
        )

    candidate = build_trade_candidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=closed_candle,
        signal=signal,
        session_key=session_decision.session_key,
    )

    trade_journal.write(
        'candidate_detected',
        {
            'symbol': symbol,
            'snapshot': snapshot,
            'candle': closed_candle,
            'signal': signal,
            'candidate': candidate,
            'session_decision': session_decision,
            'instrument_profile': risk_manager.instrument_profile_for(symbol),
            'risk_profile': risk_manager.risk_profile_for(symbol),
            'loop_id': loop_id,
        },
    )

    logger.info(
        'Trade candidate detected | symbol=%s | action=%s | score=%s | reason=%s',
        symbol,
        signal.action,
        candidate.score,
        candidate.rank_reason,
    )

    return candidate


def _write_rejected_decision(
    *,
    symbol: str,
    snapshot: MarketSnapshot,
    closed_candle: Candle,
    signal,
    reason: str,
    risk_manager: RiskManager,
    session_decision: TradingSessionDecision | None,
    trade_journal: JsonlJournal,
    loop_id: int | None = None,
) -> None:
    plan = TradePlan(
        approved=False,
        reason=reason,
        symbol=symbol,
        side=signal.action,
    )
    trade_journal.write(
        'decision',
        {
            'symbol': symbol,
            'snapshot': snapshot,
            'candle': closed_candle,
            'signal': signal,
            'equity': None,
            'trade_plan': plan,
            'session_decision': session_decision,
            'instrument_profile': risk_manager.instrument_profile_for(symbol),
            'risk_profile': risk_manager.risk_profile_for(symbol),
            'loop_id': loop_id,
        },
    )
    logger.debug('Trade rejected | symbol=%s | reason=%s', symbol, plan.reason)
    return None
