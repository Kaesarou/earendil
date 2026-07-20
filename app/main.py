import logging
from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.position_tracker import PositionTracker
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.analysis_journal import build_analysis_journal
from app.journal.raw_data_journal import RawDataJournal
from app.journal.jsonl_journal import JsonlJournal
from app.journal.run_manifest import (
    build_run_id,
    build_run_manifest,
    finalize_run_manifest,
    run_artifact_path,
    write_run_manifest,
)
from app.market.data_quality import MarketDataValidator
from app.market.market_context import MarketContextService
from app.market.session_timeframe_service import FullSessionMultiTimeframeService
from app.market_data.candle_stream import QualityAwareCandleBuilder
from app.market_data.models import MARKET_DATA_MODEL_VERSION
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.runtime.candidate_flow import execute_ranked_candidates
from app.runtime.factories import build_runtime_clients
from app.runtime.market_data_runtime import EventDrivenMarketRuntime
from app.runtime.pending_entry import PendingEntryManager
from app.runtime.position_lifecycle import restore_persisted_positions
from app.runtime.runtime_heartbeat import RuntimeHeartbeat
from app.runtime.trading_session_window import (
    TradingSessionState,
    trading_session_service_from_settings,
)
from app.strategies.balanced_strategy_config import BalancedStrategyConfig
from app.strategies.strategy import TrendStrategy
from app.utils.logging import configure_logging


logger = logging.getLogger(__name__)


def is_broker_authorization_error(exc: Exception) -> bool:
    response = getattr(exc, 'response', None)
    return getattr(response, 'status_code', None) in (401, 403)


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
    symbols: list[str],
) -> dict[str, QualityAwareCandleBuilder]:
    return {symbol: QualityAwareCandleBuilder() for symbol in symbols}


def build_strategies(
    symbols: list[str],
    instrument_registry: InstrumentRegistry,
) -> dict[str, TrendStrategy]:
    return {
        symbol: TrendStrategy(instrument_registry.config_for(symbol).trend)
        for symbol in symbols
    }


def build_market_data_manifest(settings: Settings) -> dict[str, object]:
    return {
        'mode': settings.market_data_mode,
        'queue_capacity': settings.market_data_queue_capacity,
        'position_silence_seconds': settings.ws_position_silence_seconds,
        'global_silence_seconds': settings.ws_global_silence_seconds,
        'rest_control_interval_seconds': settings.rest_control_interval_seconds,
        'position_fallback_interval_seconds': (
            settings.position_fallback_interval_seconds
        ),
        'decision_window_grace_seconds': settings.decision_window_grace_seconds,
    }


def main() -> None:
    started_at = datetime.now(timezone.utc)
    run_id = build_run_id(started_at)
    run_status = 'running'
    settings = get_settings()
    archived_manifest_path = run_artifact_path(
        settings.run_manifest_path,
        run_id,
    )
    archived_summary_path = run_artifact_path(
        settings.daily_summary_path,
        run_id,
    )
    configure_logging(
        level=settings.log_level,
        log_file_path=settings.app_log_path,
    )
    symbols = settings.watchlist_symbols()
    strategy_profile = BalancedStrategyConfig()
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
    manifest['schema_version'] = 10
    manifest['models']['market_data'] = MARKET_DATA_MODEL_VERSION
    manifest['runtime']['market_data'] = build_market_data_manifest(settings)
    write_run_manifest(archived_manifest_path, manifest)
    write_run_manifest(settings.run_manifest_path, manifest)

    clients = build_runtime_clients(settings)
    strategies = build_strategies(symbols, instrument_registry)
    candle_builders = build_candle_builders(symbols)
    trading_session_service = trading_session_service_from_settings(settings)
    trading_session_state = TradingSessionState()
    risk_manager = build_risk_manager(settings, instrument_registry)
    candidate_economics_estimator = build_candidate_economics_estimator(
        instrument_registry
    )
    executor = TradeExecutor(clients.execution_broker)
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
    multi_timeframe_service = FullSessionMultiTimeframeService(
        {
            symbol: instrument_registry.config_for(symbol).multi_timeframe
            for symbol in symbols
        }
    )
    trade_journal = build_analysis_journal(
        settings,
        run_id=run_id,
        profile=strategy_profile.name,
    )
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
    runtime = EventDrivenMarketRuntime(
        settings=settings,
        symbols=symbols,
        run_id=run_id,
        strategy_profile=strategy_profile,
        instrument_registry=instrument_registry,
        execution_broker=clients.execution_broker,
        rest_market_data=clients.rest_market_data,
        live_market_data=clients.live_market_data,
        strategies=strategies,
        candle_builders=candle_builders,
        trading_session_service=trading_session_service,
        trading_session_state=trading_session_state,
        risk_manager=risk_manager,
        candidate_economics_estimator=candidate_economics_estimator,
        executor=executor,
        position_tracker=position_tracker,
        position_store=position_store,
        cooldown_store=cooldown_store,
        cooldown_guard=cooldown_guard,
        pending_entry_manager=pending_entry_manager,
        market_data_validator=market_data_validator,
        market_context_service=market_context_service,
        multi_timeframe_service=multi_timeframe_service,
        trade_journal=trade_journal,
        market_journal=market_journal,
        candle_journal=candle_journal,
        heartbeat=heartbeat,
        is_broker_authorization_error=is_broker_authorization_error,
    )
    trade_journal.write(
        'runtime_started',
        {
            'run_id': run_id,
            'symbols': symbols,
            'strategy_profile': strategy_profile.name,
            'market_data_version': MARKET_DATA_MODEL_VERSION,
            'market_data_mode': settings.market_data_mode,
        },
    )
    logger.info(
        'Starting Goblin! | run_id=%s | broker=%s | market_data=%s | '
        'strategy_profile=%s | watchlist=%s',
        run_id,
        settings.broker,
        settings.market_data_mode,
        strategy_profile.name,
        symbols,
    )

    try:
        restore_persisted_positions(
            position_store=position_store,
            position_tracker=position_tracker,
            risk_manager=risk_manager,
            broker=clients.execution_broker,
            trade_journal=trade_journal,
            cooldown_store=cooldown_store,
            is_broker_authorization_error=is_broker_authorization_error,
        )
        run_status = runtime.run()
    except Exception as exc:
        run_status = 'failed'
        if is_broker_authorization_error(exc):
            logger.critical('Broker authorization failed. Stopping Goblin.')
            trade_journal.write(
                'broker_authorization_error',
                {'stage': 'event_runtime', 'message': str(exc)},
            )
        else:
            logger.exception('Goblin runtime failed: %s', exc)
            trade_journal.write(
                'error',
                {'stage': 'event_runtime', 'message': str(exc)},
            )
        raise
    finally:
        if run_status == 'running':
            run_status = 'completed'
        for symbol in symbols:
            runtime._write_partial_timeframe_bars(
                symbol,
                multi_timeframe_service.reset_symbol(symbol),
            )
        trade_journal.write(
            'runtime_stopped',
            {
                'run_id': run_id,
                'status': run_status,
                'loop_id': runtime.loop_id,
            },
        )
        summary = trade_journal.finalize()
        summary['schema_version'] = 10
        summary.setdefault('market_data', {})['model_version'] = (
            MARKET_DATA_MODEL_VERSION
        )
        write_run_manifest(settings.daily_summary_path, summary)
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
