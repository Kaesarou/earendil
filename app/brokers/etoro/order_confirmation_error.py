from __future__ import annotations

from datetime import datetime


class EtoroOrderConfirmationUnknownError(RuntimeError):
    def __init__(
        self,
        *,
        order_id: str,
        reference_id: str | None,
        symbol: str,
        side: str,
        amount: float,
        submitted_at: datetime,
        cause: Exception,
    ) -> None:
        self.order_id = order_id
        self.reference_id = reference_id
        self.symbol = symbol
        self.side = side
        self.amount = amount
        self.submitted_at = submitted_at
        self.cause = cause
        super().__init__(
            'eToro order confirmation unknown: '
            f'order_id={order_id}, reference_id={reference_id}, '
            f'symbol={symbol}, side={side}, amount={amount}, cause={cause}'
        )
