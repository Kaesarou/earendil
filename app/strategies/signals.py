from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    action: str  # BUY, SELL, CLOSE, HOLD
    confidence: float
    reason: str

    @staticmethod
    def hold(reason: str = 'no_signal') -> 'Signal':
        return Signal(action='HOLD', confidence=0.0, reason=reason)
