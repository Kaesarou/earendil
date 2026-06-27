import logging
import time
from dataclasses import dataclass, field

from app.brokers.base import BrokerClient
from app.market.models import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    expires_at: float
    value: object


@dataclass
class CachedBrokerClient(BrokerClient):
    delegate: BrokerClient
    market_snapshot_ttl_seconds: float = 0.0
    account_equity_ttl_seconds: float = 0.0
    position_status_ttl_seconds: float = 0.0
    batch_market_rates_enabled: bool = True
    logging_enabled: bool = False
    batch_retry_after_seconds: float = 300.0
    market_snapshot_cache: dict[str, CacheEntry] = field(default_factory=dict)
    account_equity_cache: CacheEntry | None = None
    position_status_cache: dict[str, CacheEntry] = field(default_factory=dict)
    batch_market_rates_disabled_until: float = 0.0

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return self.get_market_snapshots([symbol])[symbol]

    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        snapshots: dict[str, MarketSnapshot] = {}
        symbols_to_load: list[str] = []
        seen_symbols: set[str] = set()

        for symbol in symbols:
            normalized_symbol = self._normalize_symbol(symbol)
            if normalized_symbol in seen_symbols:
                continue
            seen_symbols.add(normalized_symbol)

            cached_snapshot = self._get_cache_entry(
                cache=self.market_snapshot_cache,
                key=normalized_symbol,
                cache_name='market_snapshot',
            )
            if cached_snapshot is None:
                symbols_to_load.append(symbol)
            else:
                snapshots[symbol] = cached_snapshot

        if symbols_to_load:
            loaded_snapshots = self._load_market_snapshots(symbols_to_load)
            for symbol, snapshot in loaded_snapshots.items():
                snapshots[symbol] = snapshot
                self._put_cache_entry(
                    cache=self.market_snapshot_cache,
                    key=self._normalize_symbol(symbol),
                    value=snapshot,
                    ttl_seconds=self.market_snapshot_ttl_seconds,
                )

        return {symbol: snapshots[symbol] for symbol in symbols if symbol in snapshots}

    def get_account_equity(self) -> float:
        now = self._now()
        if (
            self.account_equity_ttl_seconds > 0
            and self.account_equity_cache is not None
            and self.account_equity_cache.expires_at > now
        ):
            self._log_cache_hit('account_equity', 'account')
            return float(self.account_equity_cache.value)

        self._log_cache_miss('account_equity', 'account')
        equity = self.delegate.get_account_equity()
        self.account_equity_cache = self._build_entry(equity, self.account_equity_ttl_seconds)
        return equity

    def open_position(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float) -> str:
        position_id = self.delegate.open_position(symbol, side, amount, stop_loss, take_profit)
        self.invalidate_account_and_positions()
        return position_id

    def close_position(self, position_id: str) -> None:
        self.delegate.close_position(position_id)
        self.invalidate_account_and_positions()
        self.position_status_cache.pop(position_id, None)

    def is_position_open(self, position_id: str) -> bool:
        cached_status = self._get_cache_entry(
            cache=self.position_status_cache,
            key=position_id,
            cache_name='position_status',
        )
        if cached_status is not None:
            return bool(cached_status)

        is_open = self.delegate.is_position_open(position_id)
        self._put_cache_entry(
            cache=self.position_status_cache,
            key=position_id,
            value=is_open,
            ttl_seconds=self.position_status_ttl_seconds,
        )
        return is_open

    def remember_position_instrument(self, position_id: str, symbol: str) -> None:
        if hasattr(self.delegate, 'remember_position_instrument'):
            self.delegate.remember_position_instrument(position_id, symbol)

    def invalidate_market_snapshot(self, symbol: str | None = None) -> None:
        if symbol is None:
            self.market_snapshot_cache.clear()
            return
        self.market_snapshot_cache.pop(self._normalize_symbol(symbol), None)

    def invalidate_account_and_positions(self) -> None:
        self.account_equity_cache = None
        self.position_status_cache.clear()

    def _load_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        if self._should_use_batch_market_rates():
            try:
                return self._load_batch_market_snapshots(symbols)
            except Exception as exc:
                if self._is_broker_auth_error(exc):
                    raise
                self._disable_batch_market_rates_temporarily(exc)

        return {symbol: self.delegate.get_market_snapshot(symbol) for symbol in symbols}

    def _load_batch_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        if self._looks_like_etoro_delegate():
            return self._load_etoro_search_market_snapshots(symbols)

        return self.delegate.get_market_snapshots(symbols)

    def _load_etoro_search_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        normalized_symbols = [self._normalize_symbol(symbol) for symbol in symbols]
        items_by_symbol = self._load_etoro_search_items_until_symbols_found(normalized_symbols)

        missing_symbols = [symbol for symbol in normalized_symbols if symbol not in items_by_symbol]
        if missing_symbols:
            raise ValueError(f'Missing search market data for symbols={missing_symbols}')

        snapshots: dict[str, MarketSnapshot] = {}
        for symbol in symbols:
            normalized_symbol = self._normalize_symbol(symbol)
            snapshots[symbol] = self._to_market_snapshot_from_search_item(
                symbol=symbol,
                item=items_by_symbol[normalized_symbol],
            )

        logger.info('eToro batch market snapshots resolved from paginated search | symbols=%s', list(snapshots))
        return snapshots

    def _load_etoro_search_items_until_symbols_found(self, normalized_symbols: list[str]) -> dict[str, dict]:
        target_symbols = set(normalized_symbols)
        found_items: dict[str, dict] = {}
        page_number = 1
        page_size = 500

        while target_symbols - set(found_items):
            payload = self.delegate._get(
                '/api/v1/market-data/search',
                params={
                    'fields': 'instrumentId,internalSymbolFull,cvtBid,cvtAsk,currentRate',
                    'pageSize': page_size,
                    'pageNumber': page_number,
                },
            )
            items = self.delegate._extract_items(payload)
            if not items:
                break

            for item in items:
                symbol = item.get('internalSymbolFull')
                if symbol is None:
                    continue

                normalized_symbol = self._normalize_symbol(str(symbol))
                if normalized_symbol in target_symbols:
                    found_items[normalized_symbol] = item

            if len(items) < page_size:
                break

            page_number += 1

        return found_items

    def _looks_like_etoro_delegate(self) -> bool:
        return all(hasattr(self.delegate, name) for name in ('_get', '_extract_items'))

    def _to_market_snapshot_from_search_item(self, symbol: str, item: dict) -> MarketSnapshot:
        bid = self._extract_required_float(item, ('cvtBid', 'CvtBid', 'bid', 'Bid', 'bidPrice'))
        ask = self._extract_required_float(item, ('cvtAsk', 'CvtAsk', 'ask', 'Ask', 'askPrice'))
        last = self._extract_optional_float(
            item,
            ('currentRate', 'CurrentRate', 'last', 'Last', 'lastPrice', 'price', 'Price'),
        )
        if last is None:
            last = (bid + ask) / 2
        return MarketSnapshot.now(symbol=symbol, bid=bid, ask=ask, last=last)

    def _extract_required_float(self, payload: dict, keys: tuple[str, ...]) -> float:
        value = self._extract_optional_float(payload, keys)
        if value is None:
            raise ValueError(f'Unable to extract required float keys={keys}')
        return value

    def _extract_optional_float(self, payload: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return float(value)
        return None

    def _should_use_batch_market_rates(self) -> bool:
        return self.batch_market_rates_enabled and self.batch_market_rates_disabled_until <= self._now()

    def _disable_batch_market_rates_temporarily(self, exc: Exception) -> None:
        self.batch_market_rates_disabled_until = self._now() + self.batch_retry_after_seconds
        logger.warning(
            'Batch market snapshot loading failed; falling back to per-symbol loading | retry_after_seconds=%s | error=%s',
            self.batch_retry_after_seconds,
            exc,
        )

    def _is_broker_auth_error(self, exc: Exception) -> bool:
        response = getattr(exc, 'response', None)
        status_code = getattr(response, 'status_code', None)
        return status_code in (401, 403)

    def _get_cache_entry(self, cache: dict[str, CacheEntry], key: str, cache_name: str):
        entry = cache.get(key)
        now = self._now()
        if entry is None:
            self._log_cache_miss(cache_name, key)
            return None
        if entry.expires_at <= now:
            cache.pop(key, None)
            self._log_cache_miss(cache_name, key)
            return None
        self._log_cache_hit(cache_name, key)
        return entry.value

    def _put_cache_entry(self, cache: dict[str, CacheEntry], key: str, value, ttl_seconds: float) -> None:
        if ttl_seconds > 0:
            cache[key] = self._build_entry(value, ttl_seconds)

    def _build_entry(self, value, ttl_seconds: float) -> CacheEntry | None:
        if ttl_seconds <= 0:
            return None
        return CacheEntry(expires_at=self._now() + ttl_seconds, value=value)

    def _log_cache_hit(self, cache_name: str, key: str) -> None:
        if self.logging_enabled:
            logger.info('Broker cache hit | cache=%s | key=%s', cache_name, key)

    def _log_cache_miss(self, cache_name: str, key: str) -> None:
        if self.logging_enabled:
            logger.info('Broker cache miss | cache=%s | key=%s', cache_name, key)

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()

    def _now(self) -> float:
        return time.monotonic()
