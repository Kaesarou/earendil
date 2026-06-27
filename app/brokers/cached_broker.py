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
    logging_enabled: bool = False
    market_snapshot_cache: dict[str, CacheEntry] = field(default_factory=dict)
    account_equity_cache: CacheEntry | None = None
    position_status_cache: dict[str, CacheEntry] = field(default_factory=dict)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized_symbol = self._normalize_symbol(symbol)
        cached_snapshot = self._get_cache_entry(
            cache=self.market_snapshot_cache,
            key=normalized_symbol,
            cache_name='market_snapshot',
        )
        if cached_snapshot is not None:
            return cached_snapshot

        snapshot = self.delegate.get_market_snapshot(symbol)
        self._put_cache_entry(
            cache=self.market_snapshot_cache,
            key=normalized_symbol,
            value=snapshot,
            ttl_seconds=self.market_snapshot_ttl_seconds,
        )
        return snapshot

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
        if self.account_equity_ttl_seconds > 0:
            self.account_equity_cache = CacheEntry(
                expires_at=now + self.account_equity_ttl_seconds,
                value=equity,
            )
        return equity

    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> str:
        position_id = self.delegate.open_position(
            symbol=symbol,
            side=side,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
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

    def _get_cache_entry(
        self,
        cache: dict[str, CacheEntry],
        key: str,
        cache_name: str,
    ):
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

    def _put_cache_entry(
        self,
        cache: dict[str, CacheEntry],
        key: str,
        value,
        ttl_seconds: float,
    ) -> None:
        if ttl_seconds <= 0:
            return

        cache[key] = CacheEntry(
            expires_at=self._now() + ttl_seconds,
            value=value,
        )

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
