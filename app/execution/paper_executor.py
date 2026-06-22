import logging

from app.brokers.base import BrokerClient
from app.risk.risk_manager import TradePlan

logger = logging.getLogger(__name__)


class PaperExecutor:
    def __init__(self, broker: BrokerClient):
        self.broker = broker

    def execute(self, plan: TradePlan) -> str | None:
        if not plan.approved:
            logger.info('Trade rejected: %s', plan.reason)
            return None

        if not all([plan.symbol, plan.side, plan.amount, plan.stop_loss, plan.take_profit]):
            raise ValueError(f'Invalid trade plan: {plan}')

        position_id = self.broker.open_position(
            symbol=plan.symbol,
            side=plan.side,
            amount=plan.amount,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
        )
        logger.info('Paper position opened: %s', position_id)
        return position_id
