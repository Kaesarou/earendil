import logging
import time

from app.brokers.base import BrokerClient
from app.brokers.etoro_client import EtoroClient
from app.brokers.fake_broker import FakeBrokerClient
from app.config.settings import Settings, get_settings
from app.execution.position_tracker import PositionTracker
from app.execution.trade_executor import TradeExecutor
from app.journal.jsonl_journal import JsonlJournal
from app.market.candle_builder import CandleBuilder
from app.risk.position_sizing import build_position_sizing_strategy
from app.risk.risk_manager import RiskManager
from app.strategies.base import InvestmentStrategy
from app.strategies.factory import build_investment_strategy
from app.utils.logging import configure_logging
from app.risk.models import TradePlan
from app.execution.candidate_ranking import (
    build_trade_candidate,
    rank_trade_candidates,
)
from app.execution.trade_candidate import TradeCandidate

logger = logging.getLogger(__name__)


def build_market_data_broker(settings: Settings) -> BrokerClient:
    if settings.broker == 'etoro':
        return EtoroClient(settings=settings)

    if settings.broker == 'fake':
        return FakeBrokerClient(equity=50.0)

    raise ValueError(f'Unsupported market data broker: {settings.broker}')


def build_execution_broker(settings: Settings) -> BrokerClient:
    if settings.ear_mode == 'paper':
        return FakeBrokerClient(equity=50.0)

    if settings.ear_mode == 'real':
        return EtoroClient(settings=settings)

    raise ValueError(f'Unsupported execution mode: {settings.ear_mode}')


def build_risk_manager(settings: Settings) -> RiskManager:
    return RiskManager(
        settings=settings,
        position_sizing_strategy=build_position_sizing_strategy(settings),
    )


def build_candle_builders(
    settings: Settings,
    symbols: list[str],
) -> dict[str, CandleBuilder]:
    return {
        symbol: CandleBuilder(
            timeframe_seconds=settings.candle_timeframe_seconds,
        )
        for symbol in symbols
    }


def build_strategies(
    settings: Settings,
    symbols: list[str],
) -> dict[str, InvestmentStrategy]:
    return {
        symbol: build_investment_strategy(settings)
        for symbol in symbols
    }


def process_symbol(
    symbol: str,
    market_data_broker: BrokerClient,
    execution_broker: BrokerClient,
    strategy: InvestmentStrategy,
    risk_manager: RiskManager,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    candle_builder: CandleBuilder,
    trade_journal: JsonlJournal,
    market_journal: JsonlJournal,
    candle_journal: JsonlJournal,
) -> TradeCandidate | None:
    snapshot = market_data_broker.get_market_snapshot(symbol)
    market_journal.write('market_snapshot', {'symbol': symbol, 'snapshot': snapshot})

    close_signals = position_tracker.evaluate_snapshot(snapshot)
    for close_signal in close_signals:
        try:
            executor.close(close_signal.position_id)
            closed_position = position_tracker.record_closed_position(close_signal)
            risk_manager.record_close_position(close_signal.symbol)

            trade_journal.write(
                'position_closed',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'closed_position': closed_position,
                },
            )

        except Exception as exc:
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
        return

    candle_journal.write(
        'candle_closed',
        {
            'symbol': symbol,
            'candle': closed_candle,
        },
    )

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
            },
        )

        logger.info('Trade rejected: %s', plan.reason)
        return

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
) -> None:
    if not candidates:
        return

    ranked_candidates = rank_trade_candidates(candidates)

    trade_journal.write(
        'candidate_ranking',
        {
            'candidates': ranked_candidates,
        },
    )

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

            trade_journal.write(
                'position_opened',
                {
                    'symbol': candidate.symbol,
                    'position_id': position_id,
                    'position': tracked_position,
                    'candidate': candidate,
                    'trade_plan': plan,
                },
            )

        except Exception as exc:
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
    configure_logging(settings.log_level)

    symbols = settings.watchlist_symbols()

    logger.info(
        'Starting Eärendil | mode=%s | broker=%s | etoro_env=%s | real_trading_enabled=%s | strategy=%s | risk_strategy=%s | watchlist=%s',
        settings.ear_mode,
        settings.broker,
        settings.etoro_env,
        settings.real_trading_enabled,
        settings.investment_strategy,
        settings.risk_strategy,
        symbols,
    )

    if settings.ear_mode == 'real' and not settings.real_trading_enabled:
        logger.warning(
            'Real execution mode is selected but REAL_TRADING_ENABLED=false. Orders will be blocked.'
        )

    market_data_broker = build_market_data_broker(settings)
    execution_broker = build_execution_broker(settings)

    strategies = build_strategies(settings, symbols)
    candle_builders = build_candle_builders(settings, symbols)

    risk_manager = build_risk_manager(settings)
    executor = TradeExecutor(execution_broker)
    position_tracker = PositionTracker()

    trade_journal = JsonlJournal(settings.journal_path)
    market_journal = JsonlJournal(settings.market_log_path)
    candle_journal = JsonlJournal(settings.candle_journal_path)

    while True:
        try:
            candidates: list[TradeCandidate] = []

            for symbol in symbols:
                try:
                    candidate = process_symbol(
                        symbol=symbol,
                        market_data_broker=market_data_broker,
                        execution_broker=execution_broker,
                        strategy=strategies[symbol],
                        risk_manager=risk_manager,
                        executor=executor,
                        position_tracker=position_tracker,
                        candle_builder=candle_builders[symbol],
                        trade_journal=trade_journal,
                        market_journal=market_journal,
                        candle_journal=candle_journal,
                    )

                    if candidate is not None:
                        candidates.append(candidate)

                except Exception as exc:
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
                        },
                    )

            execute_ranked_candidates(
                candidates=candidates,
                execution_broker=execution_broker,
                risk_manager=risk_manager,
                executor=executor,
                position_tracker=position_tracker,
                trade_journal=trade_journal,
            )

        except KeyboardInterrupt:
            logger.info('Stopping Eärendil')
            break

        except Exception as exc:
            logger.exception('Bot loop error: %s', exc)
            trade_journal.write(
                'error',
                {
                    'message': str(exc),
                },
            )

        time.sleep(settings.poll_interval_seconds)


if __name__ == '__main__':
    main()