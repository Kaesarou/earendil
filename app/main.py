import logging
import time
from datetime import datetime, timezone

from app.brokers.base import BrokerClient
from app.config.settings import Settings, get_settings
from app.execution.candidate_economics import (
    CandidateEconomicsEstimator,
    EvaluatedTradeCandidate,
)
from app.execution.candidate_ranking import build_trade_candidate, rank_trade_candidates
from app.execution.candidate_selector import (
    CandidateSelectionResult,
    EvaluatedCandidateSelectionResult,
    RejectedCandidateSelection,
    RejectedEvaluatedCandidateSelection,
    rank_evaluated_trade_candidates,
    select_evaluated_trade_candidates,
    select_trade_candidates,
)
from app.execution.position_tracker import ClosedPosition, PositionTracker, TrackedPosition
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.jsonl_journal import JsonlJournal
from app.market.candle_builder import CandleBuilder
from app.market.models import MarketSnapshot
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.models import TradePlan
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown import build_trade_cooldown_entry
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.runtime.factories import build_broker
from app.strategies.strategy import (
    StrategyProfileConfig,
    TrendStrategy,
    strategy_profile_from_name,
)
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def is_broker_authorization_error(exc: Exception) -> bool:
    response = getattr(exc, 'response', None)
    status_code = getattr(response, 'status_code', None)
    return status_code in (401, 403)


def build_risk_manager(
    settings: Settings,
    instrument_registry: InstrumentRegistry,
) -> RiskManager:
    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=instrument_registry,
    )

def build_candidate_economics_estimator(
    instrument_registry: InstrumentRegistry,
) -> CandidateEconomicsEstimator:
    return CandidateEconomicsEstimator(
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=instrument_registry,
    )

def build_candle_builders(
    settings: Settings,
    symbols: list[str],
) -> dict[str, CandleBuilder]:
    return {
        symbol: CandleBuilder(timeframe_seconds=settings.candle_timeframe_seconds)
        for symbol in symbols
    }


def build_strategy_profile(settings: Settings) -> StrategyProfileConfig:
    return strategy_profile_from_name(settings.strategy_aggressiveness)


def build_strategies(
    symbols: list[str],
    instrument_registry: InstrumentRegistry,
) -> dict[str, TrendStrategy]:
    return {
        symbol: TrendStrategy(instrument_registry.config_for(symbol).trend)
        for symbol in symbols
    }


def register_trade_cooldown_for_closed_position(
    *,
    closed_position: ClosedPosition | None,
    risk_manager: RiskManager,
    cooldown_store: TradeCooldownStore,
    trade_journal: JsonlJournal,
) -> None:
    if closed_position is None:
        return

    cooldown_config = risk_manager.risk_profile_for(closed_position.symbol).trade_cooldown
    if not cooldown_config.enabled:
        return

    entry = build_trade_cooldown_entry(
        symbol=closed_position.symbol,
        side=closed_position.side,
        config=cooldown_config,
        raw_close_reason=closed_position.close_reason,
        closed_at=closed_position.closed_at,
        position_id=closed_position.position_id,
        gross_pnl=closed_position.gross_pnl,
        gross_pnl_percent=closed_position.gross_pnl_percent,
    )
    saved_entry = cooldown_store.save_or_extend(entry)

    trade_journal.write(
        'trade_cooldown_registered',
        {
            'source': 'bot_close',
            'entry': saved_entry,
            'closed_position': closed_position,
        },
    )
    logger.info(
        'Trade cooldown registered | source=bot_close | symbol=%s | side=%s | reason=%s | expires_at=%s',
        saved_entry.symbol,
        saved_entry.side,
        saved_entry.close_reason.value,
        saved_entry.expires_at.isoformat(),
    )


def register_trade_cooldown_for_missing_position(
    *,
    position: TrackedPosition,
    closed_at: datetime,
    risk_manager: RiskManager,
    cooldown_store: TradeCooldownStore,
    trade_journal: JsonlJournal,
) -> None:
    cooldown_config = risk_manager.risk_profile_for(position.symbol).trade_cooldown
    if not cooldown_config.enabled:
        return

    entry = build_trade_cooldown_entry(
        symbol=position.symbol,
        side=position.side,
        config=cooldown_config,
        raw_close_reason='broker_position_missing',
        closed_at=closed_at,
        position_id=position.position_id,
    )
    saved_entry = cooldown_store.save_or_extend(entry)

    trade_journal.write(
        'trade_cooldown_registered',
        {
            'source': 'broker_reconciliation',
            'entry': saved_entry,
            'position': position,
        },
    )
    logger.info(
        'Trade cooldown registered | source=broker_reconciliation | symbol=%s | side=%s | reason=%s | expires_at=%s',
        saved_entry.symbol,
        saved_entry.side,
        saved_entry.close_reason.value,
        saved_entry.expires_at.isoformat(),
    )


def reconcile_externally_closed_positions(
    *,
    broker: BrokerClient,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    position_store: PositionStore,
    cooldown_store: TradeCooldownStore,
    trade_journal: JsonlJournal,
) -> None:
    for position in position_tracker.open_positions_snapshot():
        try:
            if broker.is_position_open(position.position_id):
                continue
        except Exception as exc:
            if is_broker_authorization_error(exc):
                raise

            logger.exception(
                'Position reconciliation check failed | position_id=%s | symbol=%s | error=%s',
                position.position_id,
                position.symbol,
                exc,
            )
            trade_journal.write(
                'position_reconciliation_warning',
                {'position': position, 'message': str(exc)},
            )
            continue

        removed_position = position_tracker.remove_position(position.position_id)
        if removed_position is None:
            continue

        closed_at = datetime.now(timezone.utc)
        risk_manager.record_close_position(removed_position.symbol)

        try:
            position_store.delete_open_position(removed_position.position_id)
        except Exception as exc:
            logger.exception(
                'Position persistence delete error | position_id=%s | error=%s',
                removed_position.position_id,
                exc,
            )
            trade_journal.write(
                'position_persistence_error',
                {
                    'symbol': removed_position.symbol,
                    'position_id': removed_position.position_id,
                    'message': str(exc),
                },
            )

        register_trade_cooldown_for_missing_position(
            position=removed_position,
            closed_at=closed_at,
            risk_manager=risk_manager,
            cooldown_store=cooldown_store,
            trade_journal=trade_journal,
        )

        logger.warning(
            'Tracked position no longer open at broker | position_id=%s | symbol=%s | side=%s',
            removed_position.position_id,
            removed_position.symbol,
            removed_position.side,
        )
        trade_journal.write(
            'position_reconciled_closed',
            {
                'source': 'runtime_broker_reconciliation',
                'position': removed_position,
                'closed_at': closed_at,
            },
        )


def restore_persisted_positions(
    position_store: PositionStore,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    broker: BrokerClient,
    trade_journal: JsonlJournal,
    cooldown_store: TradeCooldownStore | None = None,
) -> None:
    restored_positions = position_store.load_open_positions()

    if not restored_positions:
        logger.info('No persisted open positions to restore')
        return

    logger.warning(
        'Restoring persisted open positions | count=%s',
        len(restored_positions),
    )

    for position in restored_positions:
        try:
            if not broker.is_position_open(position.position_id):
                closed_at = datetime.now(timezone.utc)
                logger.warning(
                    'Persisted position no longer open at broker | position_id=%s | symbol=%s',
                    position.position_id,
                    position.symbol,
                )
                position_store.delete_open_position(position.position_id)

                if cooldown_store is not None:
                    register_trade_cooldown_for_missing_position(
                        position=position,
                        closed_at=closed_at,
                        risk_manager=risk_manager,
                        cooldown_store=cooldown_store,
                        trade_journal=trade_journal,
                    )

                trade_journal.write(
                    'position_reconciled_closed',
                    {
                        'source': 'startup_broker_reconciliation',
                        'position': position,
                        'closed_at': closed_at,
                    },
                )
                continue

        except Exception as exc:
            if is_broker_authorization_error(exc):
                logger.critical(
                    'Broker authorization failed during position reconciliation. Stopping before restoring unverified positions | position_id=%s | symbol=%s | error=%s',
                    position.position_id,
                    position.symbol,
                    exc,
                )
                trade_journal.write(
                    'broker_authorization_error',
                    {
                        'stage': 'position_reconciliation',
                        'position': position,
                        'message': str(exc),
                    },
                )
                raise

            logger.exception(
                'Position reconciliation check failed | position_id=%s | symbol=%s | error=%s',
                position.position_id,
                position.symbol,
                exc,
            )
            trade_journal.write(
                'position_reconciliation_warning',
                {'position': position, 'message': str(exc)},
            )

        position_tracker.restore_open_position(position)
        risk_manager.restore_open_position(position.symbol)

        if hasattr(broker, 'remember_position_instrument'):
            try:
                broker.remember_position_instrument(
                    position_id=position.position_id,
                    symbol=position.symbol,
                )
            except Exception as exc:
                if is_broker_authorization_error(exc):
                    logger.critical(
                        'Broker authorization failed during position restore. Stopping before continuing | position_id=%s | symbol=%s | error=%s',
                        position.position_id,
                        position.symbol,
                        exc,
                    )
                    trade_journal.write(
                        'broker_authorization_error',
                        {
                            'stage': 'position_restore',
                            'position': position,
                            'message': str(exc),
                        },
                    )
                    raise

                logger.exception(
                    'Failed to restore broker instrument mapping | position_id=%s | symbol=%s | error=%s',
                    position.position_id,
                    position.symbol,
                    exc,
                )
                trade_journal.write(
                    'position_restore_warning',
                    {'position': position, 'message': str(exc)},
                )

        trade_journal.write(
            'position_restored',
            {
                'position': position,
                'instrument_profile': risk_manager.instrument_profile_for(position.symbol),
                'risk_profile': risk_manager.risk_profile_for(position.symbol),
            },
        )


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
    position_store: PositionStore | None = None,
    cooldown_store: TradeCooldownStore | None = None,
    snapshot: MarketSnapshot | None = None,
) -> TradeCandidate | None:
    snapshot = snapshot or broker.get_market_snapshot(symbol)
    market_journal.write('market_snapshot', {'symbol': symbol, 'snapshot': snapshot})
    strategy.on_snapshot(snapshot)

    close_signals = position_tracker.evaluate_snapshot(snapshot)
    for close_signal in close_signals:
        try:
            executor.close(close_signal.position_id)
            closed_position = position_tracker.record_closed_position(close_signal)
            risk_manager.record_close_position(close_signal.symbol)

            if position_store is not None:
                try:
                    position_store.delete_open_position(close_signal.position_id)
                except Exception as exc:
                    logger.exception(
                        'Position persistence delete error | position_id=%s | error=%s',
                        close_signal.position_id,
                        exc,
                    )
                    trade_journal.write(
                        'position_persistence_error',
                        {
                            'symbol': symbol,
                            'position_id': close_signal.position_id,
                            'message': str(exc),
                        },
                    )

            if cooldown_store is not None:
                register_trade_cooldown_for_closed_position(
                    closed_position=closed_position,
                    risk_manager=risk_manager,
                    cooldown_store=cooldown_store,
                    trade_journal=trade_journal,
                )

            trade_journal.write(
                'position_closed',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'closed_position': closed_position,
                },
            )

        except Exception as exc:
            if is_broker_authorization_error(exc):
                raise

            logger.exception(
                'Position close error | symbol=%s | position_id=%s | reason=%s | error=%s',
                symbol,
                close_signal.position_id,
                close_signal.reason,
                exc,
            )
            trade_journal.write(
                'position_close_error',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'message': str(exc),
                },
            )

    closed_candle = candle_builder.on_snapshot(snapshot)
    if closed_candle is None:
        return None

    candle_journal.write('candle_closed', {'symbol': symbol, 'candle': closed_candle})

    logger.info(
        'Candle closed | symbol=%s | open=%s | high=%s | low=%s | close=%s | opened_at=%s | closed_at=%s',
        closed_candle.symbol,
        closed_candle.open,
        closed_candle.high,
        closed_candle.low,
        closed_candle.close,
        closed_candle.opened_at.isoformat(),
        closed_candle.closed_at.isoformat(),
    )

    signal = strategy.on_candle(closed_candle)
    logger.info(
        'Strategy signal | symbol=%s | action=%s | confidence=%s | reason=%s | candle_close=%s',
        symbol,
        signal.action,
        signal.confidence,
        signal.reason,
        closed_candle.close,
    )

    if signal.action == 'HOLD':
        plan = TradePlan(
            approved=False,
            reason=signal.reason,
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
                'instrument_profile': risk_manager.instrument_profile_for(symbol),
                'risk_profile': risk_manager.risk_profile_for(symbol),
            },
        )
        logger.info('Trade rejected: %s', plan.reason)
        return None

    candidate = build_trade_candidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=closed_candle,
        signal=signal,
    )

    trade_journal.write(
        'candidate_detected',
        {
            'symbol': symbol,
            'snapshot': snapshot,
            'candle': closed_candle,
            'signal': signal,
            'candidate': candidate,
            'instrument_profile': risk_manager.instrument_profile_for(symbol),
            'risk_profile': risk_manager.risk_profile_for(symbol),
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


def select_trade_candidates_with_strategy_profile(
    candidates: list[TradeCandidate],
    risk_manager: RiskManager,
    strategy_profile: StrategyProfileConfig,
) -> CandidateSelectionResult:
    selected_candidates: list[TradeCandidate] = []
    rejected_candidates: list[RejectedCandidateSelection] = []
    top_n_limits: list[int] = []

    for candidate in rank_trade_candidates(candidates):
        asset_class = risk_manager.instrument_profile_for(candidate.symbol).asset_class
        candidate_selection_config = strategy_profile.candidate_selection_config_for_asset_class(asset_class)
        top_n_limits.append(candidate_selection_config.top_n)

        candidate_selection_result = select_trade_candidates([candidate], candidate_selection_config)
        if candidate_selection_result.selected_candidates:
            selected_candidates.append(candidate)
        else:
            rejected_candidates.extend(candidate_selection_result.rejected_candidates)

    positive_top_n_limits = [limit for limit in top_n_limits if limit > 0]
    top_n = min(positive_top_n_limits) if positive_top_n_limits else 0

    if top_n > 0 and len(selected_candidates) > top_n:
        kept_candidates = selected_candidates[:top_n]
        overflow_candidates = selected_candidates[top_n:]
        rejected_candidates.extend(
            RejectedCandidateSelection(
                candidate=candidate,
                reason='candidate_selection_outside_top_n',
            )
            for candidate in overflow_candidates
        )
        selected_candidates = kept_candidates

    return CandidateSelectionResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )

def select_evaluated_trade_candidates_with_strategy_profile(
    evaluated_candidates: list[EvaluatedTradeCandidate],
    risk_manager: RiskManager,
    strategy_profile: StrategyProfileConfig,
) -> EvaluatedCandidateSelectionResult:
    selected_candidates: list[EvaluatedTradeCandidate] = []
    rejected_candidates: list[RejectedEvaluatedCandidateSelection] = []
    top_n_limits: list[int] = []

    for evaluated_candidate in rank_evaluated_trade_candidates(evaluated_candidates):
        candidate = evaluated_candidate.candidate
        asset_class = risk_manager.instrument_profile_for(candidate.symbol).asset_class
        candidate_selection_config = strategy_profile.candidate_selection_config_for_asset_class(asset_class)
        top_n_limits.append(candidate_selection_config.top_n)

        candidate_selection_result = select_evaluated_trade_candidates(
            [evaluated_candidate],
            candidate_selection_config,
        )

        if candidate_selection_result.selected_candidates:
            selected_candidates.append(evaluated_candidate)
        else:
            rejected_candidates.extend(candidate_selection_result.rejected_candidates)

    positive_top_n_limits = [limit for limit in top_n_limits if limit > 0]
    top_n = min(positive_top_n_limits) if positive_top_n_limits else 0

    if top_n > 0 and len(selected_candidates) > top_n:
        kept_candidates = selected_candidates[:top_n]
        overflow_candidates = selected_candidates[top_n:]
        rejected_candidates.extend(
            RejectedEvaluatedCandidateSelection(
                evaluated_candidate=evaluated_candidate,
                reason='candidate_selection_outside_top_n',
            )
            for evaluated_candidate in overflow_candidates
        )
        selected_candidates = kept_candidates

    return EvaluatedCandidateSelectionResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )

def _legacy_selection_result_from_evaluated(
    selection_result: EvaluatedCandidateSelectionResult,
) -> CandidateSelectionResult:
    return CandidateSelectionResult(
        selected_candidates=[
            evaluated_candidate.candidate
            for evaluated_candidate in selection_result.selected_candidates
        ],
        rejected_candidates=[
            RejectedCandidateSelection(
                candidate=rejected.evaluated_candidate.candidate,
                reason=rejected.reason,
            )
            for rejected in selection_result.rejected_candidates
        ],
    )

def apply_trade_cooldown_guard(
    *,
    candidates: list[TradeCandidate],
    risk_manager: RiskManager,
    cooldown_guard: TradeCooldownGuard,
    trade_journal: JsonlJournal,
) -> list[TradeCandidate]:
    now = datetime.now(timezone.utc)
    cooldown_guard.store.delete_expired(now)
    filter_result = cooldown_guard.filter_candidates(
        candidates=candidates,
        risk_manager=risk_manager,
        now=now,
    )

    if not filter_result.rejected_candidates:
        return filter_result.selected_candidates

    trade_journal.write(
        'trade_cooldown_guard',
        {
            'selected_candidates': filter_result.selected_candidates,
            'rejected_candidates': filter_result.rejected_candidates,
        },
    )

    for rejected_candidate in filter_result.rejected_candidates:
        candidate = rejected_candidate.candidate
        decision = rejected_candidate.decision
        plan = TradePlan(
            approved=False,
            reason=decision.reason or 'trade_cooldown_active',
            symbol=candidate.symbol,
            side=candidate.signal.action,
        )
        trade_journal.write(
            'decision',
            {
                'symbol': candidate.symbol,
                'snapshot': candidate.snapshot,
                'candle': candidate.candle,
                'signal': candidate.signal,
                'candidate': candidate,
                'equity': None,
                'trade_plan': plan,
                'cooldown': decision.active_cooldown,
                'cooldown_remaining_seconds': decision.remaining_seconds,
                'instrument_profile': risk_manager.instrument_profile_for(candidate.symbol),
                'risk_profile': risk_manager.risk_profile_for(candidate.symbol),
            },
        )
        logger.info(
            'Trade rejected by cooldown | symbol=%s | action=%s | reason=%s | remaining_seconds=%s',
            candidate.symbol,
            candidate.signal.action,
            plan.reason,
            decision.remaining_seconds,
        )

    return filter_result.selected_candidates


def execute_ranked_candidates(
    candidates: list[TradeCandidate],
    execution_broker: BrokerClient,
    risk_manager: RiskManager,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    trade_journal: JsonlJournal,
    position_store: PositionStore | None = None,
    strategy_profile: StrategyProfileConfig | None = None,
    cooldown_guard: TradeCooldownGuard | None = None,
    candidate_economics_estimator: CandidateEconomicsEstimator | None = None,
) -> None:
    if not candidates:
        return

    if cooldown_guard is not None:
        candidates = apply_trade_cooldown_guard(
            candidates=candidates,
            risk_manager=risk_manager,
            cooldown_guard=cooldown_guard,
            trade_journal=trade_journal,
        )
        if not candidates:
            return

    selected_evaluated_candidates: list[EvaluatedTradeCandidate] | None = None
    rejected_evaluated_candidates: list[RejectedEvaluatedCandidateSelection] | None = None

    if candidate_economics_estimator is None:
        if strategy_profile is None:
            ranked_candidates = rank_trade_candidates(candidates)
            candidate_selection_result = CandidateSelectionResult(
                selected_candidates=ranked_candidates,
                rejected_candidates=[],
            )
        else:
            candidate_selection_result = select_trade_candidates_with_strategy_profile(
                candidates=candidates,
                risk_manager=risk_manager,
                strategy_profile=strategy_profile,
            )
            ranked_candidates = candidate_selection_result.selected_candidates

    else:
        equity_for_candidate_selection = execution_broker.get_account_equity()

        evaluated_candidates = [
            candidate_economics_estimator.evaluate(
                candidate=candidate,
                account_equity=equity_for_candidate_selection,
            )
            for candidate in candidates
        ]

        trade_journal.write(
            'candidate_economics',
            {
                'equity': equity_for_candidate_selection,
                'evaluated_candidates': evaluated_candidates,
            },
        )

        if strategy_profile is None:
            evaluated_selection_result = EvaluatedCandidateSelectionResult(
                selected_candidates=rank_evaluated_trade_candidates(evaluated_candidates),
                rejected_candidates=[],
            )
        else:
            evaluated_selection_result = select_evaluated_trade_candidates_with_strategy_profile(
                evaluated_candidates=evaluated_candidates,
                risk_manager=risk_manager,
                strategy_profile=strategy_profile,
            )

        selected_evaluated_candidates = evaluated_selection_result.selected_candidates
        rejected_evaluated_candidates = evaluated_selection_result.rejected_candidates

        candidate_selection_result = _legacy_selection_result_from_evaluated(
            evaluated_selection_result
        )
        ranked_candidates = candidate_selection_result.selected_candidates

    trade_journal.write(
        'candidate_selection',
        {
            'strategy_profile': strategy_profile.name if strategy_profile else None,
            'selected_candidates': candidate_selection_result.selected_candidates,
            'rejected_candidates': candidate_selection_result.rejected_candidates,
            'selected_evaluated_candidates': selected_evaluated_candidates,
            'rejected_evaluated_candidates': rejected_evaluated_candidates,
        },
    )
    logger.info(
        'Candidate selection | profile=%s | selected=%s | rejected=%s',
        strategy_profile.name if strategy_profile else None,
        [candidate.symbol for candidate in candidate_selection_result.selected_candidates],
        [
            {
                'symbol': rejected.candidate.symbol,
                'reason': rejected.reason,
            }
            for rejected in candidate_selection_result.rejected_candidates
        ],
    )

    if not ranked_candidates:
        return
    
    candidate_economics_by_id = {
        id(evaluated_candidate.candidate): evaluated_candidate.economics
        for evaluated_candidate in selected_evaluated_candidates or []
    }

    trade_journal.write(
        'candidate_ranking',
        {
            'candidates': ranked_candidates,
            'evaluated_candidates': selected_evaluated_candidates,
        },
    )

    logger.info(
        'Candidate ranking | candidates=%s',
        [
            {
                'symbol': candidate.symbol,
                'action': candidate.signal.action,
                'score': candidate.score,
                'expected_net_profit': (
                    round(candidate_economics_by_id[id(candidate)].expected_net_profit, 4)
                    if id(candidate) in candidate_economics_by_id
                    else None
                ),
                'expected_net_profit_percent': (
                    round(candidate_economics_by_id[id(candidate)].expected_net_profit_percent, 4)
                    if id(candidate) in candidate_economics_by_id
                    else None
                ),
                'reason': candidate.rank_reason,
            }
            for candidate in ranked_candidates
        ],
    )

    for candidate in ranked_candidates:
        try:
            equity = execution_broker.get_account_equity()
            plan = risk_manager.evaluate(
                signal=candidate.signal,
                snapshot=candidate.snapshot,
                account_equity=equity,
            )
            instrument_profile = risk_manager.instrument_profile_for(candidate.symbol)
            risk_profile = risk_manager.risk_profile_for(candidate.symbol)
            candidate_economics = candidate_economics_by_id.get(id(candidate))

            trade_journal.write(
                'decision',
                {
                    'symbol': candidate.symbol,
                    'snapshot': candidate.snapshot,
                    'candle': candidate.candle,
                    'signal': candidate.signal,
                    'candidate': candidate,
                    'candidate_economics': candidate_economics,
                    'equity': equity,
                    'trade_plan': plan,
                    'instrument_profile': instrument_profile,
                    'risk_profile': risk_profile,
                },
            )

            position_id = executor.execute(plan)
            if not position_id:
                continue

            tracked_position = position_tracker.record_open_position(
                position_id=position_id,
                trade_plan=plan,
                entry_price=candidate.snapshot.last,
            )
            risk_manager.record_open_position(candidate.symbol)

            if position_store is not None:
                try:
                    position_store.save_open_position(tracked_position)
                except Exception as exc:
                    logger.exception(
                        'Position persistence save error | position_id=%s | symbol=%s | error=%s',
                        tracked_position.position_id,
                        tracked_position.symbol,
                        exc,
                    )
                    trade_journal.write(
                        'position_persistence_error',
                        {
                            'symbol': tracked_position.symbol,
                            'position_id': tracked_position.position_id,
                            'position': tracked_position,
                            'message': str(exc),
                        },
                    )

            trade_journal.write(
                'position_opened',
                {
                    'symbol': candidate.symbol,
                    'position_id': position_id,
                    'position': tracked_position,
                    'candidate': candidate,
                    'candidate_economics': candidate_economics,
                    'trade_plan': plan,
                    'instrument_profile': instrument_profile,
                    'risk_profile': risk_profile,
                },
            )

        except Exception as exc:
            if is_broker_authorization_error(exc):
                raise

            logger.exception(
                'Candidate execution error | symbol=%s | action=%s | score=%s | error=%s',
                candidate.symbol,
                candidate.signal.action,
                candidate.score,
                exc,
            )
            trade_journal.write(
                'candidate_execution_error',
                {
                    'symbol': candidate.symbol,
                    'candidate': candidate,
                    'message': str(exc),
                },
            )
            continue


def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, log_file_path=settings.app_log_path)

    symbols = settings.watchlist_symbols()

    strategy_profile = build_strategy_profile(settings)
    instrument_registry = InstrumentRegistry(
        settings,
        instrument_configs=strategy_profile.instrument_configs,
    )

    instrument_registry.validate_supported_symbols(symbols)

    logger.info(
        'Starting Eärendil | broker=%s | strategy_profile=%s | watchlist=%s',
        settings.broker,
        strategy_profile.name,
        symbols,
    )

    broker = build_broker(settings)
    strategies = build_strategies(
        symbols=symbols,
        instrument_registry=instrument_registry,
    )
    candle_builders = build_candle_builders(settings, symbols)
    risk_manager = build_risk_manager(settings=settings, instrument_registry=instrument_registry)
    candidate_economics_estimator = build_candidate_economics_estimator(
        instrument_registry=instrument_registry,
    )
    executor = TradeExecutor(broker)
    position_tracker = PositionTracker()
    position_store = PositionStore(settings.position_store_path)
    cooldown_store = TradeCooldownStore(settings.position_store_path)
    cooldown_guard = TradeCooldownGuard(cooldown_store)

    trade_journal = JsonlJournal(settings.journal_path)
    market_journal = JsonlJournal(settings.market_log_path)
    candle_journal = JsonlJournal(settings.candle_journal_path)

    try:
        restore_persisted_positions(
            position_store=position_store,
            position_tracker=position_tracker,
            risk_manager=risk_manager,
            broker=broker,
            trade_journal=trade_journal,
            cooldown_store=cooldown_store,
        )
    except Exception as exc:
        if is_broker_authorization_error(exc):
            logger.critical('Broker authorization failed during startup. Check broker credentials.')
            return

        raise
    while True:
        try:
            cooldown_store.delete_expired(datetime.now(timezone.utc))
            reconcile_externally_closed_positions(
                broker=broker,
                position_tracker=position_tracker,
                risk_manager=risk_manager,
                position_store=position_store,
                cooldown_store=cooldown_store,
                trade_journal=trade_journal,
            )

            candidates: list[TradeCandidate] = []
            snapshots = broker.get_market_snapshots(symbols)
            for symbol in symbols:
                try:
                    candidate = process_symbol(
                        symbol=symbol,
                        broker=broker,
                        strategy=strategies[symbol],
                        risk_manager=risk_manager,
                        executor=executor,
                        position_tracker=position_tracker,
                        candle_builder=candle_builders[symbol],
                        trade_journal=trade_journal,
                        market_journal=market_journal,
                        candle_journal=candle_journal,
                        position_store=position_store,
                        cooldown_store=cooldown_store,
                        snapshot=snapshots[symbol],
                    )

                    if candidate is not None:
                        candidates.append(candidate)

                except Exception as exc:
                    if is_broker_authorization_error(exc):
                        raise

                    logger.exception('Symbol processing error | symbol=%s | error=%s', symbol, exc)
                    trade_journal.write('error', {'symbol': symbol, 'message': str(exc)})

            execute_ranked_candidates(
                candidates=candidates,
                execution_broker=broker,
                risk_manager=risk_manager,
                executor=executor,
                position_tracker=position_tracker,
                trade_journal=trade_journal,
                position_store=position_store,
                strategy_profile=strategy_profile,
                cooldown_guard=cooldown_guard,
                candidate_economics_estimator=candidate_economics_estimator,
            )

        except KeyboardInterrupt:
            logger.info('Stopping Eärendil')
            break
        except Exception as exc:
            if is_broker_authorization_error(exc):
                logger.critical('Broker authorization failed. Stopping bot loop.')
                trade_journal.write(
                    'broker_authorization_error',
                    {'stage': 'bot_loop', 'message': str(exc)},
                )
                break

            logger.exception('Bot loop error: %s', exc)
            trade_journal.write('error', {'message': str(exc)})

        time.sleep(settings.poll_interval_seconds)


if __name__ == '__main__':
    main()
