import logging
import time
from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.position_tracker import PositionTracker
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass
from app.journal.analysis_journal import build_analysis_journal
from app.journal.jsonl_journal import JsonlJournal
from app.journal.raw_data_journal import RawDataJournal
from app.journal.run_manifest import build_run_id, build_run_manifest, finalize_run_manifest, run_artifact_path, write_run_manifest
from app.market.candle_builder import CandleBuilder
from app.market.data_quality import MarketDataStatus, MarketDataValidator
from app.market.market_context import MarketContextService
from app.market.multi_timeframe import MultiTimeframeService, expected_sampling_quality
from app.market.timeframes import BarCompleteness
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.runtime.candidate_flow import execute_ranked_candidates
from app.runtime.factories import build_broker
from app.runtime.pending_entry import PendingEntryManager
from app.runtime.pending_entry_flow import write_pending_events
from app.runtime.position_lifecycle import reconcile_externally_closed_positions, restore_persisted_positions
from app.runtime.runtime_heartbeat import RuntimeHeartbeat
from app.runtime.session_force_close import force_close_positions_before_session_end
from app.runtime.session_runtime import filter_symbols_by_trading_session
from app.runtime.symbol_flow import process_symbol
from app.runtime.trading_session_window import TradingSessionState, trading_session_service_from_settings
from app.strategies.balanced_strategy_config import BalancedStrategyConfig
from app.strategies.strategy import TrendStrategy
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def is_broker_authorization_error(exc: Exception) -> bool:
    response = getattr(exc, 'response', None)
    return getattr(response, 'status_code', None) in (401, 403)


def build_risk_manager(settings: Settings, instrument_registry: InstrumentRegistry) -> RiskManager:
    return RiskManager(settings=settings, position_sizing_strategy=FixedPercentPositionSizing(), instrument_registry=instrument_registry)


def build_candidate_economics_estimator(instrument_registry: InstrumentRegistry) -> CandidateEconomicsEstimator:
    return CandidateEconomicsEstimator(position_sizing_strategy=FixedPercentPositionSizing(), instrument_registry=instrument_registry)


def build_candle_builders(symbols: list[str]) -> dict[str, CandleBuilder]:
    return {symbol: CandleBuilder() for symbol in symbols}


def build_strategies(symbols: list[str], instrument_registry: InstrumentRegistry) -> dict[str, TrendStrategy]:
    return {symbol: TrendStrategy(instrument_registry.config_for(symbol).trend) for symbol in symbols}


def _context_symbols_for_active_assets(
    *,
    settings: Settings,
    instrument_registry: InstrumentRegistry,
    active_symbols: list[str],
) -> dict[str, AssetClass]:
    active_assets = {
        instrument_registry.resolve(symbol).asset_class for symbol in active_symbols
    }
    result: dict[str, AssetClass] = {}
    for asset_class, symbols in settings.benchmark_symbols_by_asset_class().items():
        if asset_class not in active_assets:
            continue
        for symbol in symbols:
            if symbol not in active_symbols:
                result[symbol] = asset_class
    return result


def _write_partial_timeframe_bars(candle_journal, symbol: str, bars, loop_id: int | None) -> None:
    for bar in bars:
        event_type = (
            'timeframe_bar_partial'
            if bar.completeness == BarCompleteness.PARTIAL
            else 'timeframe_bar_incomplete'
        )
        candle_journal.write(
            event_type,
            {
                'symbol': symbol,
                'timeframe': bar.timeframe.name.lower(),
                'timeframe_bar': bar,
                'loop_id': loop_id,
            },
        )


def main() -> None:
    started_at = datetime.now(timezone.utc)
    run_id = build_run_id(started_at)
    run_status = 'running'
    settings = get_settings()
    archived_manifest_path = run_artifact_path(settings.run_manifest_path, run_id)
    archived_summary_path = run_artifact_path(settings.daily_summary_path, run_id)
    configure_logging(level=settings.log_level, log_file_path=settings.app_log_path)
    symbols = settings.watchlist_symbols()
    strategy_profile = BalancedStrategyConfig()
    instrument_registry = InstrumentRegistry(settings, instrument_configs=strategy_profile.instrument_configs)
    instrument_registry.validate_supported_symbols(symbols)

    manifest = build_run_manifest(settings=settings, strategy_profile=strategy_profile, instrument_registry=instrument_registry, symbols=symbols, run_id=run_id, started_at=started_at, manifest_path=archived_manifest_path, summary_path=archived_summary_path)
    write_run_manifest(archived_manifest_path, manifest)
    write_run_manifest(settings.run_manifest_path, manifest)
    logger.info('Starting Goblin! | run_id=%s | broker=%s | strategy_profile=%s | watchlist=%s | journal_detail=%s', run_id, settings.broker, strategy_profile.name, symbols, settings.journal_detail_level)
    sampling_quality = expected_sampling_quality(settings.poll_interval_seconds)
    if sampling_quality.value == 'sparse':
        logger.warning(
            'Sparse M1 sampling expected | poll_interval_seconds=%s | fixed_base_timeframe_seconds=60',
            settings.poll_interval_seconds,
        )

    broker = build_broker(settings)
    strategies = build_strategies(symbols, instrument_registry)
    candle_builders = build_candle_builders(symbols)
    trading_session_service = trading_session_service_from_settings(settings)
    trading_session_state = TradingSessionState()
    risk_manager = build_risk_manager(settings, instrument_registry)
    candidate_economics_estimator = build_candidate_economics_estimator(instrument_registry)
    executor = TradeExecutor(broker)
    position_tracker = PositionTracker()
    position_store = PositionStore(settings.position_store_path)
    cooldown_store = TradeCooldownStore(settings.position_store_path)
    cooldown_guard = TradeCooldownGuard(cooldown_store)
    pending_entry_manager = PendingEntryManager()
    market_data_validator = MarketDataValidator()
    market_context_service = MarketContextService(
        instrument_registry=instrument_registry,
        benchmark_symbols=settings.benchmark_symbols_by_asset_class(),
    )
    multi_timeframe_service = MultiTimeframeService(
        {
            symbol: instrument_registry.config_for(symbol).multi_timeframe
            for symbol in symbols
        }
    )
    trade_journal = build_analysis_journal(settings, run_id=run_id, profile=strategy_profile.name)
    market_journal = RawDataJournal(JsonlJournal(settings.market_log_path, run_id=run_id, stream_name='market'), trade_journal.record_raw_event)
    candle_journal = RawDataJournal(JsonlJournal(settings.candle_journal_path, run_id=run_id, stream_name='candles'), trade_journal.record_raw_event)
    heartbeat = RuntimeHeartbeat(settings.runtime_heartbeat_minutes)
    loop_id = 0
    trade_journal.write('runtime_started', {'run_id': run_id, 'symbols': symbols, 'strategy_profile': strategy_profile.name})

    try:
        try:
            restore_persisted_positions(position_store=position_store, position_tracker=position_tracker, risk_manager=risk_manager, broker=broker, trade_journal=trade_journal, cooldown_store=cooldown_store, is_broker_authorization_error=is_broker_authorization_error)
        except Exception as exc:
            if is_broker_authorization_error(exc):
                run_status = 'failed'
                logger.critical('Broker authorization failed during startup.')
                return
            raise

        while True:
            loop_id += 1
            try:
                loop_now = datetime.now(timezone.utc)
                cooldown_store.delete_expired(loop_now)
                reconcile_externally_closed_positions(broker=broker, position_tracker=position_tracker, risk_manager=risk_manager, position_store=position_store, cooldown_store=cooldown_store, trade_journal=trade_journal, is_broker_authorization_error=is_broker_authorization_error)
                candidates: list[TradeCandidate] = []
                symbols_to_fetch, session_decisions, started_symbols, completed_session_keys = filter_symbols_by_trading_session(symbols=symbols, instrument_registry=instrument_registry, trading_session_service=trading_session_service, trading_session_state=trading_session_state, now=loop_now)
                for session_key in completed_session_keys:
                    risk_manager.reset_session_trades(session_key)
                    market_context_service.reset_session(session_key)
                    write_pending_events(trade_journal, pending_entry_manager.invalidate_session(session_key))
                    trade_journal.write('session_trades_reset', {'session_key': session_key, 'loop_id': loop_id})
                for symbol in started_symbols:
                    market_data_validator.reset_symbol(symbol)
                    _write_partial_timeframe_bars(
                        candle_journal,
                        symbol,
                        multi_timeframe_service.reset_symbol(symbol),
                        loop_id,
                    )
                    candle_builders[symbol] = CandleBuilder()
                    strategies[symbol] = TrendStrategy(instrument_registry.config_for(symbol).trend)
                    trade_journal.write('session_started', {'symbol': symbol, 'session_decision': session_decisions[symbol], 'loop_id': loop_id})
                for symbol, session_decision in session_decisions.items():
                    trade_journal.write('session_state', {'symbol': symbol, 'session_decision': session_decision, 'loop_id': loop_id})

                trading_snapshots = broker.get_market_snapshots(symbols_to_fetch) if symbols_to_fetch else {}
                context_asset_classes = _context_symbols_for_active_assets(
                    settings=settings,
                    instrument_registry=instrument_registry,
                    active_symbols=symbols_to_fetch,
                )
                context_snapshots = {}
                if context_asset_classes:
                    try:
                        context_snapshots = broker.get_market_snapshots(list(context_asset_classes))
                    except Exception as exc:
                        if is_broker_authorization_error(exc):
                            raise
                        trade_journal.write('market_context_fetch_error', {'symbols': list(context_asset_classes), 'message': str(exc), 'loop_id': loop_id})

                all_snapshots = {**context_snapshots, **trading_snapshots}
                requested_symbols = [*symbols_to_fetch, *context_asset_classes]
                for symbol, snapshot in all_snapshots.items():
                    market_journal.write('market_snapshot_received', {'symbol': symbol, 'snapshot': snapshot, 'loop_id': loop_id})
                quality_configs = {
                    symbol: instrument_registry.config_for(symbol).market_data_quality
                    for symbol in symbols_to_fetch
                }
                quality_configs.update(
                    {
                        symbol: strategy_profile.instrument_config_for_asset_class(asset_class).market_data_quality
                        for symbol, asset_class in context_asset_classes.items()
                    }
                )
                validated_batch = market_data_validator.validate_batch(
                    loop_id=loop_id,
                    requested_symbols=requested_symbols,
                    snapshots=all_snapshots,
                    configs=quality_configs,
                    now=loop_now,
                )
                trade_journal.write('market_batch_validated', {'batch': validated_batch, 'loop_id': loop_id})
                for result in validated_batch.results.values():
                    if result.status == MarketDataStatus.ACCEPTED:
                        if result.reasons:
                            trade_journal.write('market_data_jump_confirmed', {'symbol': result.symbol, 'validation': result, 'loop_id': loop_id})
                    elif result.status == MarketDataStatus.QUARANTINED:
                        trade_journal.write('market_data_quarantined', {'symbol': result.symbol, 'validation': result, 'loop_id': loop_id})
                    else:
                        trade_journal.write('market_data_rejected', {'symbol': result.symbol, 'validation': result, 'loop_id': loop_id})

                market_context_service.update(
                    snapshots=validated_batch.accepted,
                    session_decisions=session_decisions,
                    context_asset_classes=context_asset_classes,
                )

                for symbol in symbols_to_fetch:
                    snapshot = validated_batch.accepted.get(symbol)
                    if snapshot is None:
                        continue
                    try:
                        session_decision = session_decisions[symbol]
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
                            is_broker_authorization_error=is_broker_authorization_error,
                            position_store=position_store,
                            cooldown_store=cooldown_store,
                            snapshot=snapshot,
                            session_decision=session_decision,
                            loop_id=loop_id,
                            pending_entry_manager=pending_entry_manager,
                            cooldown_guard=cooldown_guard,
                            market_context_service=market_context_service,
                            multi_timeframe_service=multi_timeframe_service,
                            run_id=run_id,
                        )
                        force_close_positions_before_session_end(symbol=symbol, snapshot=snapshot, session_decision=session_decision, executor=executor, position_tracker=position_tracker, risk_manager=risk_manager, trade_journal=trade_journal, position_store=position_store, cooldown_store=cooldown_store, is_broker_authorization_error=is_broker_authorization_error)
                        if candidate is not None:
                            candidates.append(candidate)
                    except Exception as exc:
                        if is_broker_authorization_error(exc):
                            raise
                        logger.exception('Symbol processing error | symbol=%s | error=%s', symbol, exc)
                        trade_journal.write('error', {'symbol': symbol, 'message': str(exc), 'loop_id': loop_id})
                execute_ranked_candidates(candidates=candidates, execution_broker=broker, risk_manager=risk_manager, executor=executor, position_tracker=position_tracker, trade_journal=trade_journal, position_store=position_store, strategy_profile=strategy_profile, cooldown_guard=cooldown_guard, candidate_economics_estimator=candidate_economics_estimator, is_broker_authorization_error=is_broker_authorization_error, pending_entry_manager=pending_entry_manager)
                heartbeat.maybe_emit(journal=trade_journal, logger=logger, metrics=trade_journal.runtime_metrics(), open_positions=len(position_tracker.open_positions_snapshot()), active_symbols=len(symbols_to_fetch))
            except KeyboardInterrupt:
                run_status = 'stopped'
                trade_journal.write('runtime_interrupted', {'run_id': run_id, 'loop_id': loop_id})
                logger.info('Stopping Goblin!')
                break
            except Exception as exc:
                if is_broker_authorization_error(exc):
                    run_status = 'failed'
                    logger.critical('Broker authorization failed. Stopping bot loop.')
                    trade_journal.write('broker_authorization_error', {'stage': 'bot_loop', 'message': str(exc), 'loop_id': loop_id})
                    break
                logger.exception('Bot loop error: %s', exc)
                trade_journal.write('error', {'message': str(exc), 'loop_id': loop_id})
            time.sleep(settings.poll_interval_seconds)
    except Exception:
        run_status = 'failed'
        raise
    finally:
        if run_status == 'running':
            run_status = 'completed'
        for symbol in symbols:
            _write_partial_timeframe_bars(
                candle_journal,
                symbol,
                multi_timeframe_service.reset_symbol(symbol),
                loop_id,
            )
        trade_journal.write('runtime_stopped', {'run_id': run_id, 'status': run_status, 'loop_id': loop_id})
        summary = trade_journal.finalize()
        write_run_manifest(archived_summary_path, summary)
        finalize_run_manifest(archived_manifest_path, status=run_status, summary=summary)
        finalize_run_manifest(settings.run_manifest_path, status=run_status, summary=summary)


if __name__ == '__main__':
    main()
