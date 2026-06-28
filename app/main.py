import logging
import time

from app.brokers.base import BrokerClient
from app.brokers.cached_broker import CachedBrokerClient
from app.brokers.etoro_client import EtoroClient
from app.brokers.fake_broker import FakeBrokerClient
from app.config.settings import Settings, get_settings
from app.execution.candidate_ranking import build_trade_candidate
from app.execution.position_tracker import PositionTracker
from app.execution.pre_scan import PreScanConfig, pre_scan_candidates
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.jsonl_journal import JsonlJournal
from app.market.candle_builder import CandleBuilder
from app.market.models import MarketSnapshot
from app.persistence.position_store import PositionStore
from app.risk.models import TradePlan
from app.risk.position_sizing import build_position_sizing_strategy
from app.risk.risk_manager import RiskManager
from app.strategies.base import InvestmentStrategy
from app.strategies.factory import build_investment_strategy
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def is_broker_authorization_error(exc: Exception) -> bool:
    response = getattr(exc, 'response', None)
    status_code = getattr(response, 'status_code', None)
    return status_code in (401, 403)


def with_api_cache(settings: Settings, broker: BrokerClient) -> BrokerClient:
    if not settings.api_cache_enabled:
        return broker

    return CachedBrokerClient(
        delegate=broker,
        market_snapshot_ttl_seconds=settings.market_snapshot_cache_ttl_seconds,
        account_equity_ttl_seconds=settings.account_equity_cache_ttl_seconds,
        position_status_ttl_seconds=settings.position_status_cache_ttl_seconds,
        batch_market_rates_enabled=settings.market_rates_batch_enabled,
        logging_enabled=settings.api_cache_logging_enabled,
    )


def build_market_data_broker(settings: Settings) -> BrokerClient:
    if settings.broker == 'etoro':
        return with_api_cache(settings, EtoroClient(settings=settings))

    if settings.broker == 'fake':
        return with_api_cache(settings, FakeBrokerClient(equity=50.0))

    raise ValueError(f'Unsupported market data broker: {settings.broker}')


def build_execution_broker(settings: Settings) -> BrokerClient:
    if settings.ear_mode == 'paper':
        return with_api_cache(settings, FakeBrokerClient(equity=50.0))

    if settings.ear_mode == 'real':
        return with_api_cache(settings, EtoroClient(settings=settings))

    raise ValueError(f'Unsupported execution mode: {settings.ear_mode}')


def build_risk_manager(
    settings: Settings,
    instrument_registry: InstrumentRegistry,
) -> RiskManager:
    return RiskManager(
        settings=settings,
        position_sizing_strategy=build_position_sizing_strategy(settings.risk_strategy),
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


def build_strategies(
    settings: Settings,
    symbols: list[str],
) -> dict[str, InvestmentStrategy]:
    return {symbol: build_investment_strategy(settings) for symbol in symbols}


def restore_persisted_positions(
    position_store: PositionStore,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    execution_broker: BrokerClient,
    trade_journal: JsonlJournal,
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
            if not execution_broker.is_position_open(position.position_id):
                logger.warning(
                    'Persisted position no longer open at broker | position_id=%s | symbol=%s',
                    position.position_id,
                    position.symbol,
                )
                position_store.delete_open_position(position.position_id)
                trade_journal.write(
                    'position_reconciled_closed',
                    {'position': position},
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

        if hasattr(execution_broker, 'remember_position_instrument'):
            try:
                execution_broker.remember_position_instrument(
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
    market_data_broker: BrokerClient,
    strategy: InvestmentStrategy,
    risk_manager: RiskManager,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    candle_builder: CandleBuilder,
    trade_journal: JsonlJournal,
    market_journal: JsonlJournal,
    candle_journal: JsonlJournal,
    position_store: PositionStore | None = None,
    snapshot: MarketSnapshot | None = None,
) -> TradeCandidate | None:
    snapshot = snapshot or market_data_broker.get_market_snapshot(symbol)
    market_journal.write('market_snapshot', {'symbol': symbol, 'snapshot': snapshot})

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


def execute_ranked_candidates(
    candidates: list[TradeCandidate],
    execution_broker: BrokerClient,
    risk_manager: RiskManager,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    trade_journal: JsonlJournal,
    position_store: PositionStore | None = None,
    settings: Settings | None = None,
) -> None:
    if not candidates:
        return

    pre_scan_config = (
        PreScanConfig.from_settings(settings)
        if settings is not None
        else PreScanConfig(enabled=False)
    )
    pre_scan_result = pre_scan_candidates(candidates, pre_scan_config)
    ranked_candidates = pre_scan_result.selected_candidates

    if pre_scan_config.enabled:
        trade_journal.write(
            'pre_scan',
            {
                'config': pre_scan_config,
                'selected_candidates': pre_scan_result.selected_candidates,
                'rejected_candidates': pre_scan_result.rejected_candidates,
            },
        )
        logger.info(
            'Pre-scan | selected=%s | rejected=%s',
            [candidate.symbol for candidate in pre_scan_result.selected_candidates],
            [
                {
                    'symbol': rejected.candidate.symbol,
                    'reason': rejected.reason,
                }
                for rejected in pre_scan_result.rejected_candidates
            ],
        )

    if not ranked_candidates:
        return

    trade_journal.write('candidate_ranking', {'candidates': ranked_candidates})

    logger.info(
        'Candidate ranking | candidates=%s',
        [
            {
                'symbol': candidate.symbol,
                'action': candidate.signal.action,
                'score': candidate.score,
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

            trade_journal.write(
                'decision',
                {
                    'symbol': candidate.symbol,
                    'snapshot': candidate.snapshot,
                    'candle': candidate.candle,
                    'signal': candidate.signal,
                    'candidate': candidate,
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
    instrument_registry = InstrumentRegistry(settings)

    logger.info(
        'Starting Eärendil | mode=%s | broker=%s | etoro_env=%s | strategy=%s | risk_strategy=%s | watchlist=%s | api_cache_enabled=%s | market_rates_batch_enabled=%s',
        settings.ear_mode,
        settings.broker,
        settings.etoro_env,
        settings.investment_strategy,
        settings.risk_strategy,
        symbols,
        settings.api_cache_enabled,
        settings.market_rates_batch_enabled,
    )

    market_data_broker = build_market_data_broker(settings)
    execution_broker = build_execution_broker(settings)
    strategies = build_strategies(settings, symbols)
    candle_builders = build_candle_builders(settings, symbols)
    risk_manager = build_risk_manager(settings=settings, instrument_registry=instrument_registry)
    executor = TradeExecutor(execution_broker)
    position_tracker = PositionTracker()
    position_store = PositionStore(settings.position_store_path)

    trade_journal = JsonlJournal(settings.journal_path)
    market_journal = JsonlJournal(settings.market_log_path)
    candle_journal = JsonlJournal(settings.candle_journal_path)

    try:
        restore_persisted_positions(
            position_store=position_store,
            position_tracker=position_tracker,
            risk_manager=risk_manager,
            execution_broker=execution_broker,
            trade_journal=trade_journal,
        )
    except Exception as exc:
        if is_broker_authorization_error(exc):
            logger.critical(
                'Broker authorization failed during startup. Check ETORO_API_KEY / ETORO_USER_KEY and stop retrying until credentials are fixed.'
            )
            return

        raise

    while True:
        try:
            candidates: list[TradeCandidate] = []
            snapshots = market_data_broker.get_market_snapshots(symbols)
            for symbol in symbols:
                try:
                    candidate = process_symbol(
                        symbol=symbol,
                        market_data_broker=market_data_broker,
                        strategy=strategies[symbol],
                        risk_manager=risk_manager,
                        executor=executor,
                        position_tracker=position_tracker,
                        candle_builder=candle_builders[symbol],
                        trade_journal=trade_journal,
                        market_journal=market_journal,
                        candle_journal=candle_journal,
                        position_store=position_store,
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
                execution_broker=execution_broker,
                risk_manager=risk_manager,
                executor=executor,
                position_tracker=position_tracker,
                trade_journal=trade_journal,
                position_store=position_store,
                settings=settings,
            )

        except KeyboardInterrupt:
            logger.info('Stopping Eärendil')
            break
        except Exception as exc:
            if is_broker_authorization_error(exc):
                logger.critical(
                    'Broker authorization failed. Stopping bot loop instead of retrying every poll interval. Check ETORO_API_KEY / ETORO_USER_KEY.'
                )
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
