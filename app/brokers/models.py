from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerOrderResult:
    order_id: str
    reference_id: str | None
    position_id: str | None
    raw_response: dict