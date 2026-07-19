import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from app.market_data_probe.models import NormalizedCandle, NormalizedRate


@dataclass
class ObservedCandle:
    open: float
    high: float
    low: float
    close: float
    observations: int = 1

    def update(self, price: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.observations += 1


class StudyMetrics:
    def __init__(self):
        self._lock = Lock()
        self.request_counts: Counter[str] = Counter()
        self.request_failures: Counter[str] = Counter()
        self.request_durations_ms: dict[str, list[float]] = defaultdict(list)
        self.rate_counts: Counter[tuple[str, str]] = Counter()
        self.repeated_prices: Counter[tuple[str, str]] = Counter()
        self.duplicate_message_ids: Counter[tuple[str, str]] = Counter()
        self.duplicate_rate_ids: Counter[tuple[str, str]] = Counter()
        self.out_of_order_timestamps: Counter[tuple[str, str]] = Counter()
        self.state_reconstructed_observations: Counter[
            tuple[str, str]
        ] = Counter()
        self.latencies_ms: dict[tuple[str, str], list[float]] = defaultdict(list)
        self.silence_events = 0
        self.reconnections = 0
        self.connection_errors = 0
        self.authentication_successes = 0
        self._seen_message_ids: set[str] = set()
        self._seen_rate_ids: set[tuple[str, str, str]] = set()
        self._last_price: dict[tuple[str, str], tuple[float, float, float]] = {}
        self._last_source_timestamp: dict[tuple[str, str], datetime] = {}
        self._observed_candles: dict[
            tuple[str, str, datetime], ObservedCandle
        ] = {}
        self._historical_candles: dict[
            tuple[str, datetime], NormalizedCandle
        ] = {}

    def add_request(
        self,
        category: str,
        *,
        duration_ms: float,
        succeeded: bool,
    ) -> None:
        with self._lock:
            self.request_counts[category] += 1
            self.request_durations_ms[category].append(duration_ms)
            if not succeeded:
                self.request_failures[category] += 1

    def add_rate(self, rate: NormalizedRate) -> None:
        key = (rate.source, rate.symbol)
        with self._lock:
            self.rate_counts[key] += 1
            price = (rate.bid, rate.ask, rate.last)
            if self._last_price.get(key) == price:
                self.repeated_prices[key] += 1
            self._last_price[key] = price

            if rate.message_id is not None:
                if rate.message_id in self._seen_message_ids:
                    self.duplicate_message_ids[key] += 1
                self._seen_message_ids.add(rate.message_id)

            if rate.price_rate_id is not None:
                rate_key = (rate.source, rate.symbol, rate.price_rate_id)
                if rate_key in self._seen_rate_ids:
                    self.duplicate_rate_ids[key] += 1
                self._seen_rate_ids.add(rate_key)

            if rate.source_timestamp is not None:
                previous_timestamp = self._last_source_timestamp.get(key)
                if (
                    previous_timestamp is not None
                    and rate.source_timestamp < previous_timestamp
                ):
                    self.out_of_order_timestamps[key] += 1
                self._last_source_timestamp[key] = max(
                    previous_timestamp or rate.source_timestamp,
                    rate.source_timestamp,
                )
                self.latencies_ms[key].append(
                    (
                        rate.received_at - rate.source_timestamp
                    ).total_seconds()
                    * 1000
                )

            if rate.state_reconstructed:
                self.state_reconstructed_observations[key] += 1

            minute = rate.source_timestamp or rate.received_at
            minute = minute.astimezone(timezone.utc).replace(
                second=0,
                microsecond=0,
            )
            candle_key = (rate.source, rate.symbol, minute)
            candle = self._observed_candles.get(candle_key)
            if candle is None:
                self._observed_candles[candle_key] = ObservedCandle(
                    open=rate.last,
                    high=rate.last,
                    low=rate.last,
                    close=rate.last,
                )
            else:
                candle.update(rate.last)

    def add_historical_candle(self, candle: NormalizedCandle) -> None:
        if candle.potentially_incomplete:
            return
        with self._lock:
            self._historical_candles[
                (candle.symbol, candle.opened_at)
            ] = candle

    def add_silence(self) -> None:
        with self._lock:
            self.silence_events += 1

    def add_reconnection(self) -> None:
        with self._lock:
            self.reconnections += 1

    def add_connection_error(self) -> None:
        with self._lock:
            self.connection_errors += 1

    def add_authentication_success(self) -> None:
        with self._lock:
            self.authentication_successes += 1

    def summary(
        self,
        *,
        elapsed_seconds: float,
        planned_duration_seconds: float | None = None,
    ) -> dict:
        with self._lock:
            budget_duration_seconds = (
                planned_duration_seconds
                if planned_duration_seconds is not None
                else elapsed_seconds
            )
            baseline_rate_requests = max(
                1,
                math.ceil(budget_duration_seconds / 10) * 2,
            )
            actual_rate_requests = self.request_counts['rest_rates']
            reduction = (
                1 - actual_rate_requests / baseline_rate_requests
            ) * 100
            return {
                'elapsed_seconds': round(elapsed_seconds, 3),
                'requests': {
                    category: {
                        'count': count,
                        'failures': self.request_failures[category],
                        'latency_ms': _distribution(
                            self.request_durations_ms[category]
                        ),
                    }
                    for category, count in sorted(self.request_counts.items())
                },
                'request_budget': {
                    'baseline_two_batches_every_10_seconds': (
                        baseline_rate_requests
                    ),
                    'observed_rest_rate_requests': actual_rate_requests,
                    'reduction_percent': round(reduction, 3),
                    'startup_search_and_final_candle_requests_excluded': True,
                },
                'websocket': {
                    'authentication_successes': self.authentication_successes,
                    'reconnections': self.reconnections,
                    'connection_errors': self.connection_errors,
                    'silence_events': self.silence_events,
                },
                'rates': self._rate_summary(),
                'ohlc_comparison': self._ohlc_comparison(),
            }

    def _rate_summary(self) -> dict:
        result: dict[str, dict] = {}
        for source, symbol in sorted(self.rate_counts):
            key = (source, symbol)
            result.setdefault(source, {})[symbol] = {
                'observations': self.rate_counts[key],
                'repeated_prices': self.repeated_prices[key],
                'duplicate_message_ids': self.duplicate_message_ids[key],
                'duplicate_rate_ids': self.duplicate_rate_ids[key],
                'out_of_order_source_timestamps': (
                    self.out_of_order_timestamps[key]
                ),
                'state_reconstructed_observations': (
                    self.state_reconstructed_observations[key]
                ),
                'data_age_ms': _distribution(self.latencies_ms[key]),
            }
        return result

    def _ohlc_comparison(self) -> dict:
        differences: dict[tuple[str, str], list[dict[str, float]]] = (
            defaultdict(list)
        )
        for (source, symbol, minute), observed in self._observed_candles.items():
            historical = self._historical_candles.get((symbol, minute))
            if historical is None:
                continue
            reference = max(abs(historical.close), 1e-12)
            absolute_ohlc_delta_bps = (
                sum(
                    abs(actual - expected)
                    for actual, expected in (
                        (observed.open, historical.open),
                        (observed.high, historical.high),
                        (observed.low, historical.low),
                        (observed.close, historical.close),
                    )
                )
                / 4
                / reference
                * 10_000
            )
            differences[(source, symbol)].append(
                {
                    'mean_absolute_ohlc_delta_bps': absolute_ohlc_delta_bps,
                    'missed_high_bps': max(
                        0.0,
                        historical.high - observed.high,
                    )
                    / reference
                    * 10_000,
                    'missed_low_bps': max(
                        0.0,
                        observed.low - historical.low,
                    )
                    / reference
                    * 10_000,
                    'observations': float(observed.observations),
                }
            )

        result: dict[str, dict] = {}
        for (source, symbol), rows in sorted(differences.items()):
            result.setdefault(source, {})[symbol] = {
                'comparable_closed_minutes': len(rows),
                'mean_absolute_ohlc_delta_bps': _mean_field(
                    rows,
                    'mean_absolute_ohlc_delta_bps',
                ),
                'mean_missed_high_bps': _mean_field(
                    rows,
                    'missed_high_bps',
                ),
                'mean_missed_low_bps': _mean_field(
                    rows,
                    'missed_low_bps',
                ),
                'mean_observations_per_minute': _mean_field(
                    rows,
                    'observations',
                ),
            }
        return result


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {'count': 0, 'median': None, 'p95': None, 'maximum': None}
    ordered = sorted(values)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        'count': len(values),
        'median': round(statistics.median(ordered), 3),
        'p95': round(ordered[p95_index], 3),
        'maximum': round(ordered[-1], 3),
    }


def _mean_field(rows: list[dict[str, float]], field: str) -> float:
    return round(statistics.fmean(row[field] for row in rows), 6)
