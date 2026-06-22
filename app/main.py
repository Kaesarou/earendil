import logging
import time

from app.brokers.etoro_client import EtoroClient
from app.brokers.fake_broker import FakeBrokerClient
from app.config.settings import get_settings
from app.execution.paper_executor import PaperExecutor
from app.journal.jsonl_journal import JsonlJournal
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

    logger.info('Starting Eärendil | mode=%s | broker=%s', settings.ear_mode, settings.broker)

    execution_broker = build_broker(settings)
    market_data_broker = build_market_data_broker(settings)
    market_data = MarketDataService(market_data_broker)
    strategy = BreakoutStrategy()
    risk_manager = RiskManager(settings)
    executor = PaperExecutor(execution_broker)
    trade_journal = JsonlJournal(settings.journal_path)
    market_journal = JsonlJournal(settings.market_log_path)

    while True:
        try:
            snapshot = market_data.snapshot(settings.default_symbol)
            market_journal.write('market_snapshot', {'snapshot': snapshot})

            signal = strategy.on_snapshot(snapshot)
            equity = execution_broker.get_account_equity()
            plan = risk_manager.evaluate(signal, snapshot, equity)

            trade_journal.write(
                'decision',
                {
                    'snapshot': snapshot,
                    'signal': signal,
                    'equity': equity,
                    'trade_plan': plan,
                },
            )

            position_id = executor.execute(plan)
            if position_id:
                risk_manager.record_open_position()
                trade_journal.write('position_opened', {'position_id': position_id, 'trade_plan': plan})

        except KeyboardInterrupt:
            logger.info('Stopping Eärendil')
            break
        except Exception as exc:
            logger.exception('Bot loop error: %s', exc)
            trade_journal.write('error', {'message': str(exc)})

        time.sleep(settings.poll_interval_seconds)


if __name__ == '__main__':
    main()
