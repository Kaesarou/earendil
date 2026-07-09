from app.persistence.closed_trade_memory_store import ClosedTradeMemoryStore


class TradeCooldownStore(ClosedTradeMemoryStore):
    def save_or_extend(self, entry):
        return self.save_or_replace(entry)

    def find_active(self, symbol, side, now):
        return self.find_active_cooldown(symbol=symbol, side=side, now=now)
