#!/usr/bin/env python3
import argparse
import asyncio
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import Settings
from app.market_data_probe.metrics import StudyMetrics
from app.market_data_probe.models import utc_now
from app.market_data_probe.recorder import ProbeRecorder
from app.market_data_probe.rest_probe import EtoroRestProbe
from app.market_data_probe.websocket_probe import EtoroWebSocketProbe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Collect eToro demo REST and WebSocket market data without orders.'
        )
    )
    parser.add_argument(
        '--mode',
        choices=('compare', 'ws-primary'),
        required=True,
        help=(
            'compare keeps two REST batches every 10 seconds; ws-primary '
            'uses two validation batches every 60 seconds.'
        ),
    )
    parser.add_argument(
        '--symbols',
        help='Defaults to WATCHLIST from .env.',
    )
    parser.add_argument(
        '--benchmark',
        help='Defaults to MARKET_BENCHMARK_CRYPTO from .env.',
    )
    parser.add_argument(
        '--duration-seconds',
        type=float,
        help='Defaults to 1800 for compare and 3600 for ws-primary.',
    )
    parser.add_argument('--rest-interval-seconds', type=float)
    parser.add_argument('--silence-seconds', type=float, default=15.0)
    parser.add_argument(
        '--forced-reconnect-after-seconds',
        type=float,
        default=120.0,
    )
    parser.add_argument('--historical-candle-count', type=int, default=120)
    parser.add_argument('--run-id')
    parser.add_argument(
        '--output-root',
        type=Path,
        default=Path('data/market-data-study'),
    )
    return parser.parse_args()


async def run_probe(args: argparse.Namespace) -> Path:
    duration_seconds = args.duration_seconds
    if duration_seconds is None:
        duration_seconds = 1800.0 if args.mode == 'compare' else 3600.0
    if duration_seconds <= 0:
        raise ValueError('duration-seconds must be positive')
    if args.silence_seconds <= 0:
        raise ValueError('silence-seconds must be positive')
    if not 1 <= args.historical_candle_count <= 1000:
        raise ValueError('historical-candle-count must be between 1 and 1000')

    settings = Settings()
    symbols = _parse_symbols(args.symbols or settings.watchlist)
    benchmark_symbols = _parse_symbols(
        args.benchmark or settings.market_benchmark_crypto
    )
    benchmark_symbols = [
        symbol for symbol in benchmark_symbols if symbol not in symbols
    ]
    if not symbols:
        raise ValueError('At least one crypto symbol is required.')
    if not benchmark_symbols:
        raise ValueError(
            'A distinct crypto benchmark is required to preserve the '
            'runtime two-batch request baseline.'
        )

    run_id = args.run_id or _default_run_id(args.mode)
    output_directory = args.output_root / run_id
    if output_directory.exists() and any(output_directory.iterdir()):
        raise FileExistsError(
            f'Output directory is not empty: {output_directory}'
        )

    recorder = ProbeRecorder(output_directory)
    metrics = StudyMetrics()
    rest_probe = EtoroRestProbe(
        settings=settings,
        recorder=recorder,
        metrics=metrics,
    )
    all_symbols = [*symbols, *benchmark_symbols]
    instrument_id_by_symbol = await asyncio.to_thread(
        rest_probe.resolve_symbols,
        all_symbols,
    )

    rest_interval_seconds = args.rest_interval_seconds
    if rest_interval_seconds is None:
        rest_interval_seconds = 10.0 if args.mode == 'compare' else 60.0
    if rest_interval_seconds <= 0:
        raise ValueError('rest-interval-seconds must be positive')

    started_at = utc_now()
    manifest = {
        'schema_version': 1,
        'run_id': run_id,
        'mode': args.mode,
        'status': 'running',
        'started_at': started_at,
        'source_commit': _source_commit(),
        'broker_environment': 'demo',
        'orders_enabled': False,
        'decision_authorized_sources': [],
        'tradable_symbols': symbols,
        'benchmark_symbols': benchmark_symbols,
        'instrument_id_by_symbol': instrument_id_by_symbol,
        'duration_seconds': duration_seconds,
        'rest_interval_seconds': rest_interval_seconds,
        'websocket_url': EtoroWebSocketProbe.websocket_url,
        'silence_seconds': args.silence_seconds,
        'forced_reconnect_after_seconds': (
            args.forced_reconnect_after_seconds
        ),
        'official_contracts': {
            'websocket': (
                'https://api-portal.etoro.com/api-reference/websocket/'
                'example-code'
            ),
            'topics': (
                'https://api-portal.etoro.com/api-reference/websocket/topics'
            ),
            'candles': (
                'https://api-portal.etoro.com/api-reference/market-data/'
                'get-instrument-candle-history'
            ),
        },
    }
    recorder.write_json('manifest.json', manifest)

    websocket_probe = EtoroWebSocketProbe(
        api_key=settings.etoro_api_key,
        user_key=settings.etoro_user_key,
        instrument_id_by_symbol=instrument_id_by_symbol,
        recorder=recorder,
        metrics=metrics,
        silence_seconds=args.silence_seconds,
        forced_reconnect_after_seconds=(
            args.forced_reconnect_after_seconds
        ),
    )
    collection_started = time.monotonic()
    await asyncio.gather(
        websocket_probe.run(duration_seconds=duration_seconds),
        _poll_rest_rates(
            rest_probe=rest_probe,
            duration_seconds=duration_seconds,
            interval_seconds=rest_interval_seconds,
            symbols=symbols,
            benchmark_symbols=benchmark_symbols,
            instrument_id_by_symbol=instrument_id_by_symbol,
            recorder=recorder,
        ),
    )

    for symbol, instrument_id in instrument_id_by_symbol.items():
        try:
            await asyncio.to_thread(
                rest_probe.fetch_historical_candles,
                symbol=symbol,
                instrument_id=instrument_id,
                candle_count=args.historical_candle_count,
            )
        except Exception as exc:
            recorder.append(
                'events',
                {
                    'event': 'rest_candle_fetch_error',
                    'symbol': symbol,
                    'instrument_id': instrument_id,
                    'error_type': type(exc).__name__,
                    'message': str(exc),
                    'observed_at': utc_now(),
                },
            )

    elapsed_seconds = time.monotonic() - collection_started
    summary = metrics.summary(elapsed_seconds=elapsed_seconds)
    summary.update(
        {
            'schema_version': 1,
            'run_id': run_id,
            'mode': args.mode,
            'started_at': started_at,
            'completed_at': utc_now(),
            'orders_sent': 0,
        }
    )
    recorder.write_json('summary.json', summary)
    recorder.write_json(
        'manifest.json',
        {
            **manifest,
            'status': 'completed',
            'completed_at': utc_now(),
            'summary_path': 'summary.json',
        },
    )
    return output_directory


async def _poll_rest_rates(
    *,
    rest_probe: EtoroRestProbe,
    duration_seconds: float,
    interval_seconds: float,
    symbols: list[str],
    benchmark_symbols: list[str],
    instrument_id_by_symbol: dict[str, int],
    recorder: ProbeRecorder,
) -> None:
    deadline = time.monotonic() + duration_seconds
    next_poll = time.monotonic()
    groups = [('tradable', symbols), ('benchmark', benchmark_symbols)]
    while time.monotonic() < deadline:
        for group_name, group_symbols in groups:
            try:
                await asyncio.to_thread(
                    rest_probe.fetch_rates,
                    group_name=group_name,
                    symbols=group_symbols,
                    instrument_id_by_symbol=instrument_id_by_symbol,
                )
            except Exception as exc:
                recorder.append(
                    'events',
                    {
                        'event': 'rest_rates_fetch_error',
                        'group': group_name,
                        'symbols': group_symbols,
                        'error_type': type(exc).__name__,
                        'message': str(exc),
                        'observed_at': utc_now(),
                    },
                )
        next_poll += interval_seconds
        delay = min(next_poll, deadline) - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)


def _parse_symbols(raw: str) -> list[str]:
    result: list[str] = []
    for value in raw.split(','):
        symbol = value.strip().upper()
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _default_run_id(mode: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'etoro-crypto-{mode}-{timestamp}'


def _source_commit() -> str | None:
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def main() -> None:
    args = parse_args()
    output_directory = asyncio.run(run_probe(args))
    print(f'Market-data probe completed: {output_directory}')


if __name__ == '__main__':
    main()
