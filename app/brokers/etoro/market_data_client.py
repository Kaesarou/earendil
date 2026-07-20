import json
import logging
import time
from pathlib import Path

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.instrument_cache import remember_instrument_id
from app.market.models import MarketSnapshot


logger = logging.getLogger(__name__)


class EtoroRestMarketDataClient:
    def __init__(
        self,
        client: EtoroClient,
        *,
        instrument_id_cache_path: str,
        resolution_min_interval_seconds: float,
    ) -> None:
        self.client = client
        self.instrument_id_cache_path = Path(instrument_id_cache_path)
        self.resolution_min_interval_seconds = max(
            0.0,
            resolution_min_interval_seconds,
        )
        self._last_resolution_started_at: float | None = None
        self._load_instrument_id_cache()

    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        return self.client.get_market_snapshots(symbols)

    def resolve_instrument_ids(self, symbols: list[str]) -> dict[str, int]:
        normalized = list(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
        )
        resolved: dict[str, int] = {}
        for symbol in normalized:
            cached = self.client.instrument_ids_by_symbol.get(symbol)
            if cached is not None:
                resolved[symbol] = cached
                continue
            self._wait_for_resolution_slot()
            instrument_id = self.client._find_instrument_id(symbol)
            self._last_resolution_started_at = time.monotonic()
            resolved[symbol] = instrument_id
            self._write_instrument_id_cache()
        return resolved

    def _wait_for_resolution_slot(self) -> None:
        previous = self._last_resolution_started_at
        if previous is None or self.resolution_min_interval_seconds <= 0:
            return
        remaining = self.resolution_min_interval_seconds - (
            time.monotonic() - previous
        )
        if remaining > 0:
            time.sleep(remaining)

    def _load_instrument_id_cache(self) -> None:
        path = self.instrument_id_cache_path
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            logger.warning(
                'Ignoring invalid eToro instrument cache | path=%s | error=%s',
                path,
                exc,
            )
            return
        if not isinstance(payload, dict):
            logger.warning(
                'Ignoring non-object eToro instrument cache | path=%s',
                path,
            )
            return
        loaded = 0
        for raw_symbol, raw_instrument_id in payload.items():
            symbol = str(raw_symbol).strip().upper()
            try:
                instrument_id = int(raw_instrument_id)
            except (TypeError, ValueError):
                continue
            if not symbol or instrument_id <= 0:
                continue
            remember_instrument_id(
                instrument_ids_by_symbol=self.client.instrument_ids_by_symbol,
                symbol_by_instrument_id=self.client.symbol_by_instrument_id,
                symbol=symbol,
                instrument_id=instrument_id,
            )
            loaded += 1
        logger.info(
            'Loaded eToro instrument cache | path=%s | instruments=%s',
            path,
            loaded,
        )

    def _write_instrument_id_cache(self) -> None:
        path = self.instrument_id_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(
            json.dumps(
                dict(sorted(self.client.instrument_ids_by_symbol.items())),
                ensure_ascii=False,
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )
        temporary.replace(path)
