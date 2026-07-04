import logging
import time
from datetime import datetime, timezone

from app.brokers.base import BrokerClient
from app.config.settings import Settings, get_settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.candidate_ranking import build_trade_candidate
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
from app.runtime.candidate_flow import execute_ranked_candidates
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
                is_broker_authorization_error=is_broker_authorization_error,
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
