import logging
import time
from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.position_tracker import PositionTracker
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.analysis_journal import build_analysis_journal
from app.journal.jsonl_journal import JsonlJournal
from app.journal.raw_data_journal import RawDataJournal
from app.journal.run_manifest import (
    build_run_id,
    build_run_manifest,
    finalize_run_manifest,
    run_artifact_path,
    write_run_manifest,
)
from app.market.candle_builder import CandleBuilder
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.runtime.candidate_flow import execute_ranked_candidates
from app.runtime.factories import build_broker
from app.runtime.position_lifecycle import (
    reconcile_externally_closed_positions,
    restore_persisted_positions,
)
from app.runtime.runtime_heartbeat import RuntimeHeartbeat
from app.runtime.session_force_close import force_close_positions_before_session_end
from app.runtime.session_runtime import filter_symbols_by_trading_session
from app.runtime.symbol_flow import process_symbol
from app.runtime.trading_session_window import (
    TradingSessionState,
    trading_session_service_from_settings,
)
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


def main() -> None:
    started_at = datetime.now(timezone.utc)
    run_id = build_run_id(started_at)
    run_status = 'running'
    settings = get_settings()
    archived_manifest_path = run_artifact_path(settings.run_manifest_path, run_id)
    archived_summary_path = run_artifact_path(settings.daily_summary_path, run_id)
    configure_logging(level=settings.log_level, log_file_path=settings.app_log_path)
    symbols = settings.watchlist_symbols()
    strategy_profile = build_strategy_profile(settings)
    instrument_registry = InstrumentRegistry(
        settings,
        instrument_configs=strategy_profile.instrument_configs,
    )
    instrument_registry.validate_supported_symbols(symbols)

    manifest = build_run_manifest(
        settings=settings,
        strategy_profile=strategy_profile,
        instrument_registry=instrument_registry,
        symbols=symbols,
        run_id=run_id,
        started_at=started_at,
        manifest_path=archived_manifest_path,
        summary_path=archived_summary_path,
    )
    write_run_manifest(archived_manifest_path, manifest)
    write_run_manifest(settings.run_manifest_path, manifest)

    logger.info(
        'Starting Eärendil | run_id=%s | broker=%s | strategy_profile=%s | '
        'watchlist=%s | journal_detail=%s',
        run_id,
        settings.broker,
        strategy_profile.name,
        symbols,
        settings.journal_detail_level,
    )

    broker = build_broker(settings)
    strategies = build_strategies(
        symbols=symbols,
        instrument_registry=instrument_registry,
    )
    candle_builders = build_candle_builders(settings, symbols)
    trading_session_service = trading_session_service_from_settings(settings)
    trading_session_state = TradingSessionState()
    risk_manager = build_risk_manager(
        settings=settings,
        instrument_registry=instrument_registry,
    )
    candidate_economics_estimator = build_candidate_economics_estimator(
        instrument_registry=instrument_registry,
    )
    executor = TradeExecutor(broker)
    position_tracker = PositionTracker()
    position_store = PositionStore(settings.position_store_path)
    cooldown_store = TradeCooldownStore(settings.position_store_path)
    cooldown_guard = TradeCooldownGuard(cooldown_store)
    trade_journal = build_analysis_journal(settings, run_id=run_id)
    market_journal = RawDataJournal(
        JsonlJournal(
            settings.market_log_path,
            run_id=run_id,
            stream_name='market',
        ),
        trade_journal.record_raw_event,
    )
    candle_journal = RawDataJournal(
        JsonlJournal(
            settings.candle_journal_path,
            run_id=run_id,
            stream_name='candles',
        ),
        trade_journal.record_raw_event,
    )
    heartbeat = RuntimeHeartbeat(settings.runtime_heartbeat_minutes)
    loop_id = 0
    trade_journal.write(
        'runtime_started',
        {
            'run_id': run_id,
            'symbols': symbols,
            'strategy_profile': strategy_profile.name,
        },
    )

    try:
        try:
            restore_persisted_positions(
                position_store=position_store,
                position_tracker=position_tracker,
                risk_manager=risk_manager,
                broker=broker,
                trade_journal=trade_journal,
                cooldown_store=cooldown_store,
                is_broker_authorization_error=is_broker_authorization_error,
            )
        except Exception as exc:
            if is_broker_authorization_error(exc):
                run_status = 'failed'
                logger.critical(
                    'Broker authorization failed during startup. Check broker credentials.'
                )
                return
            raise

        while True:
            loop_id += 1
            try:
                cooldown_store.delete_expired(datetime.now(timezone.utc))
                reconcile_externally_closed_positions(
                    broker=broker,
                    position_tracker=position_tracker,
                    risk_manager=risk_manager,
                    position_store=position_store,
                    cooldown_store=cooldown_store,
                    trade_journal=trade_journal,
                    is_broker_authorization_error=is_broker_authorization_error,
                )
                candidates: list[TradeCandidate] = []
                (
                    symbols_to_fetch,
                    session_decisions,
                    started_symbols,
                    completed_session_keys,
                ) = filter_symbols_by_trading_session(
                    symbols=symbols,
                    instrument_registry=instrument_registry,
                    trading_session_service=trading_session_service,
                    trading_session_state=trading_session_state,
                    now=datetime.now(timezone.utc),
                )
                for session_key in completed_session_keys:
                    risk_manager.reset_session_trades(session_key)
                    trade_journal.write(
                        'session_trades_reset',
                        {'session_key': session_key, 'loop_id': loop_id},
                    )
                for symbol in started_symbols:
                    candle_builders[symbol] = CandleBuilder(
                        timeframe_seconds=settings.candle_timeframe_seconds,
                    )
                    strategies[symbol] = TrendStrategy(
                        instrument_registry.config_for(symbol).trend
                    )
                    trade_journal.write(
                        'session_started',
                        {
                            'symbol': symbol,
                            'session_decision': session_decisions[symbol],
                            'loop_id': loop_id,
                        },
                    )
                for symbol, session_decision in session_decisions.items():
                    trade_journal.write(
                        'session_state',
                        {
                            'symbol': symbol,
                            'session_decision': session_decision,
                            'loop_id': loop_id,
                        },
                    )

                snapshots = (
                    broker.get_market_snapshots(symbols_to_fetch)
                    if symbols_to_fetch
                    else {}
                )
                for symbol in symbols_to_fetch:
                    try:
                        session_decision = session_decisions[symbol]
                        snapshot = snapshots[symbol]
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
                            is_broker_authorization_error=(
                                is_broker_authorization_error
                            ),
                            position_store=position_store,
                            cooldown_store=cooldown_store,
                            snapshot=snapshot,
                            session_decision=session_decision,
                            loop_id=loop_id,
                        )
                        force_close_positions_before_session_end(
                            symbol=symbol,
                            snapshot=snapshot,
                            session_decision=session_decision,
                            executor=executor,
                            position_tracker=position_tracker,
                            risk_manager=risk_manager,
                            trade_journal=trade_journal,
                            position_store=position_store,
                            cooldown_store=cooldown_store,
                            is_broker_authorization_error=(
                                is_broker_authorization_error
                            ),
                        )
                        if candidate is not None:
                            candidates.append(candidate)
                    except Exception as exc:
                        if is_broker_authorization_error(exc):
                            raise
                        logger.exception(
                            'Symbol processing error | symbol=%s | error=%s',
                            symbol,
                            exc,
                        )
                        trade_journal.write(
                            'error',
                            {
                                'symbol': symbol,
                                'message': str(exc),
                                'loop_id': loop_id,
                            },
                        )
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
                    candidate_economics_estimator=(
                        candidate_economics_estimator
                    ),
                    is_broker_authorization_error=(
                        is_broker_authorization_error
                    ),
                )
                heartbeat.maybe_emit(
                    journal=trade_journal,
                    logger=logger,
                    metrics=trade_journal.runtime_metrics(),
                    open_positions=len(
                        position_tracker.open_positions_snapshot()
                    ),
                    active_symbols=len(symbols_to_fetch),
                )
            except KeyboardInterrupt:
                run_status = 'stopped'
                trade_journal.write(
                    'runtime_interrupted',
                    {'run_id': run_id, 'loop_id': loop_id},
                )
                logger.info('Stopping Eärendil')
                break
            except Exception as exc:
                if is_broker_authorization_error(exc):
                    run_status = 'failed'
                    logger.critical(
                        'Broker authorization failed. Stopping bot loop.'
                    )
                    trade_journal.write(
                        'broker_authorization_error',
                        {
                            'stage': 'bot_loop',
                            'message': str(exc),
                            'loop_id': loop_id,
                        },
                    )
                    break
                logger.exception('Bot loop error: %s', exc)
                trade_journal.write(
                    'error',
                    {'message': str(exc), 'loop_id': loop_id},
                )
            time.sleep(settings.poll_interval_seconds)
    except Exception:
        run_status = 'failed'
        raise
    finally:
        if run_status == 'running':
            run_status = 'completed'
        trade_journal.write(
            'runtime_stopped',
            {'run_id': run_id, 'status': run_status, 'loop_id': loop_id},
        )
        summary = trade_journal.finalize()
        write_run_manifest(archived_summary_path, summary)
        finalize_run_manifest(
            archived_manifest_path,
            status=run_status,
            summary=summary,
        )
        finalize_run_manifest(
            settings.run_manifest_path,
            status=run_status,
            summary=summary,
        )


if __name__ == '__main__':
    main()
