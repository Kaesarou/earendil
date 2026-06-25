import logging
import time

from app.brokers.etoro_client import EtoroClient
from app.brokers.fake_broker import FakeBrokerClient
from app.config.settings import get_settings
from app.execution.paper_executor import PaperExecutor
from app.execution.position_tracker import PositionTracker
from app.journal.jsonl_journal import JsonlJournal
from app.market.candle_builder import CandleBuilder
from app.market.service import MarketDataService
from app.risk.risk_manager import RiskManager
from app.strategies.breakout import BreakoutStrategy
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)

def build_market_data_broker(settings):
    if settings.broker == 'etoro':
        return EtoroClient(settings=settings)

    return FakeBrokerClient(equity=50.0)

def build_broker(settings):
    if settings.ear_mode == 'paper':
        return FakeBrokerClient(equity=50.0)
    return EtoroClient(settings=settings)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info(
        'Starting Eärendil | mode=%s | broker=%s | etoro_env=%s | real_trading_enabled=%s',
        settings.ear_mode,
        settings.broker,
        settings.etoro_env,
        settings.real_trading_enabled,
    )

    if settings.ear_mode == 'real' and not settings.real_trading_enabled:
        logger.warning(
            'Real execution mode is selected but REAL_TRADING_ENABLED=false. Orders will be blocked.'
        )

    execution_broker = build_broker(settings)
    market_data_broker = build_market_data_broker(settings)
    market_data = MarketDataService(market_data_broker)
    strategy = BreakoutStrategy()
    risk_manager = RiskManager(settings)
    executor = PaperExecutor(execution_broker)
    position_tracker = PositionTracker()
    trade_journal = JsonlJournal(settings.journal_path)
    market_journal = JsonlJournal(settings.market_log_path)
    candle_builder = CandleBuilder(timeframe_seconds=60)
    candle_journal = JsonlJournal('data/logs/candles.jsonl')

    while True:
        try:
            snapshot = market_data.snapshot(settings.default_symbol)
            market_journal.write('market_snapshot', {'snapshot': snapshot})

            close_signals = position_tracker.evaluate_snapshot(snapshot)
            for close_signal in close_signals:
                executor.close(close_signal.position_id)
                closed_position = position_tracker.record_closed_position(close_signal.position_id)
                risk_manager.record_close_position()

                trade_journal.write(
                    'position_closed',
                    {
                        'close_signal': close_signal,
                        'position': closed_position,
                    },
                )

            closed_candle = candle_builder.on_snapshot(snapshot)
            if closed_candle is not None:
                candle_journal.write('candle_closed', {'candle': closed_candle})
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
                    'Strategy signal | action=%s | confidence=%s | reason=%s | candle_close=%s',
                    signal.action,
                    signal.confidence,
                    signal.reason,
                    closed_candle.close,
                )
                equity = execution_broker.get_account_equity()
                plan = risk_manager.evaluate(signal, snapshot, equity)

                trade_journal.write(
                    'decision',
                    {
                        'snapshot': snapshot,
                        'candle': closed_candle,
                        'signal': signal,
                        'equity': equity,
                        'trade_plan': plan,
                    },
                )

                position_id = executor.execute(plan)
                if position_id:
                    tracked_position = position_tracker.record_open_position(
                        position_id=position_id,
                        trade_plan=plan,
                        entry_price=snapshot.last,
                    )
                
                    risk_manager.record_open_position()
                
                    trade_journal.write(
                        'position_opened',
                        {
                            'position_id': position_id,
                            'position': tracked_position,
                            'trade_plan': plan,
                        },
                    )

        except KeyboardInterrupt:
            logger.info('Stopping Eärendil')
            break
        except Exception as exc:
            logger.exception('Bot loop error: %s', exc)
            trade_journal.write('error', {'message': str(exc)})

        time.sleep(settings.poll_interval_seconds)


if __name__ == '__main__':
    main()
