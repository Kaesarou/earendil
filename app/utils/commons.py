from app.market.models import MarketSnapshot


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()

def spread_percent(snapshot: MarketSnapshot) -> float:
    if snapshot.last <= 0:
        return 100.0

    if snapshot.bid <= 0 or snapshot.ask <= 0:
        return 100.0

    spread = max(0.0, snapshot.ask - snapshot.bid)
    return (spread / snapshot.last) * 100