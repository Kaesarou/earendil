from app.brokers.etoro_client import EtoroClient
from app.market.models import MarketSnapshot


class EtoroSearchClient(EtoroClient):
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        payload = self._get(
            '/api/v1/market-data/search',
            params={'internalSymbolFull': symbol},
        )
        item = self._find_exact_market_data_item(symbol, self._extract_items(payload))
        return self._to_market_snapshot_from_search_item(symbol, item)

    def _find_exact_market_data_item(self, symbol: str, items: list[dict]) -> dict:
        normalized_symbol = symbol.strip().upper()
        for item in items:
            item_symbol = item.get('internalSymbolFull')
            if item_symbol is None:
                continue
            if str(item_symbol).strip().upper() == normalized_symbol:
                return item

        candidates = [
            {
                'internalSymbolFull': item.get('internalSymbolFull'),
                'displayName': item.get('internalInstrumentDisplayName'),
                'instrumentId': item.get('instrumentId') or item.get('internalInstrumentId'),
                'currentRate': item.get('currentRate'),
            }
            for item in items[:10]
        ]
        raise ValueError(
            f'No exact eToro market data match found for symbol={symbol}. Candidates={candidates}'
        )

    def _to_market_snapshot_from_search_item(self, symbol: str, item: dict) -> MarketSnapshot:
        bid = self._extract_float(item, ('cvtBid', 'CvtBid', 'bid', 'Bid', 'bidPrice'))
        ask = self._extract_float(item, ('cvtAsk', 'CvtAsk', 'ask', 'Ask', 'askPrice'))
        last = self._extract_optional_float(
            item,
            ('currentRate', 'CurrentRate', 'last', 'Last', 'lastPrice', 'price', 'Price'),
        )
        if last is None:
            last = (bid + ask) / 2

        return MarketSnapshot.now(symbol=symbol, bid=bid, ask=ask, last=last)
