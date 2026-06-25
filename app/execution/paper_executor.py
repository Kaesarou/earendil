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

        symbol = plan.symbol
        side = plan.side
        amount = plan.amount
        stop_loss = plan.stop_loss
        take_profit = plan.take_profit

        if symbol is None:
            raise ValueError(f'Invalid trade plan without symbol: {plan}')

        if side is None:
            raise ValueError(f'Invalid trade plan without side: {plan}')

        if amount is None:
            raise ValueError(f'Invalid trade plan without amount: {plan}')

        if stop_loss is None:
            raise ValueError(f'Invalid trade plan without stop_loss: {plan}')

        if take_profit is None:
            raise ValueError(f'Invalid trade plan without take_profit: {plan}')

        position_id = self.broker.open_position(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.info('Paper position opened: %s', position_id)
        return position_id
    
    def close(self, position_id: str) -> None:
        self.broker.close_position(position_id)
        logger.info('Paper position closed: %s', position_id)