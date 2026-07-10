from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Signal:
    action: str  # BUY, SELL, CLOSE, HOLD
    confidence: float  # Compatibility setup-quality score. This is not a TP/SL probability.
    reason: str
    metadata: dict[str, Any] | None = None

    @property
    def setup_quality(self) -> float:
        """Heuristic quality of the recognized setup, not a win probability."""
        return self.confidence

    @staticmethod
    def hold(reason: str = 'no_signal', metadata: dict[str, Any] | None = None) -> 'Signal':
        return Signal(
            action='HOLD',
            confidence=0.0,
            reason=reason,
            metadata=metadata,
        )
