from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Signal:
    action: str  # BUY, SELL, CLOSE, HOLD
    confidence: float
    reason: str
    metadata: dict[str, Any] | None = None

    @staticmethod
    def hold(reason: str = 'no_signal', metadata: dict[str, Any] | None = None) -> 'Signal':
        return Signal(
            action='HOLD',
            confidence=0.0,
            reason=reason,
            metadata=metadata,
        )
