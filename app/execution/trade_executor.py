import logging

from app.brokers.base import (
    BrokerClient,
    ClosePositionSubmission,
    OpenPositionResult as BrokerOpenPositionResult,
)
from app.risk.models import TradePlan

logger = logging.getLogger(__name__)


class TradeExecutor:
    def __init__(self, broker: BrokerClient):
        self.broker = broker

    def execute(self, plan: TradePlan) -> BrokerOpenPositionResult | None:
        if not plan.approved:
            logger.debug('Trade rejected before broker execution: %s', plan.reason)
            return None

        symbol = self._required(plan.symbol, 'symbol', plan)
        side = self._required(plan.side, 'side', plan)
        amount = self._required(plan.amount, 'amount', plan)
        stop_loss = self._required(plan.stop_loss, 'stop_loss', plan)
        take_profit = self._required(plan.take_profit, 'take_profit', plan)

        result = self.broker.open_position(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.info('Broker result: %s', result)
        return result

    def close(self, position_id: str) -> ClosePositionSubmission:
        submission = self.broker.close_position(position_id)
        logger.info(
            'Position close submitted | position_id=%s | close_order_id=%s',
            position_id,
            submission.close_order_id,
        )
        return submission

    def _required(self, value, field_name: str, plan: TradePlan):
        if value is None:
            raise ValueError(f'Invalid trade plan without {field_name}: {plan}')
        return value
