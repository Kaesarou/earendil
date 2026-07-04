import logging
import time
from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.position_tracker import PositionTracker
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.jsonl_journal import JsonlJournal
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
from app.runtime.symbol_flow import process_symbol
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
            is_broker_authorization_error=is_broker_authorization_error,
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
                is_broker_authorization_error=is_broker_authorization_error,
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
                        is_broker_authorization_error=is_broker_authorization_error,
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
