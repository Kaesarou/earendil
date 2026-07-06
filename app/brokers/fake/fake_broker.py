import math
import time
from dataclasses import dataclass, field

from app.brokers.base import BrokerClient, OpenPositionResult
from app.market.models import MarketSnapshot


@dataclass
class FakeBrokerClient(BrokerClient):
    equity: float = 50.0
    base_price: float = 65000.0
    tick: int = 0
    positions: dict[str, dict] = field(default_factory=dict)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        self.tick += 1
        wave = math.sin(self.tick / 8) * 80
        drift = self.tick * 0.5
        last = self.base_price + wave + drift
        spread = 4.0
        return MarketSnapshot.now(symbol=symbol, bid=last - spread / 2, ask=last + spread / 2, last=last)

    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        result: dict[str, MarketSnapshot] = {}
        for symbol in symbols:
            result[symbol] = self.get_market_snapshot(symbol)
        return result

    def get_account_equity(self) -> float:
        return self.equity

    def open_position(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float) -> OpenPositionResult:
        position_id = f'paper-{int(time.time())}-{len(self.positions) + 1}'
        self.positions[position_id] = {
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
        }
        return OpenPositionResult(position_id=position_id, executed_entry_price=None)

    def close_position(self, position_id: str) -> None:
        self.positions.pop(position_id, None)

    def is_position_open(self, position_id: str) -> bool:
        return position_id in self.positions
