import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.execution.entry_decision import ENTRY_DECISION_MODEL_VERSION
from app.execution.scoring.tp_probability import TP_PROBABILITY_MODEL_VERSION
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.serialization import serialize_value
from app.market.market_context import MARKET_CONTEXT_VERSION
from app.market.multi_timeframe import expected_sampling_quality
from app.market.timeframes import (
    BASE_TIMEFRAME,
    MULTI_TIMEFRAME_MODEL_VERSION,
    SUPPORTED_TIMEFRAMES,
)

_SENSITIVE_SETTINGS = {
    'ETORO_API_KEY',
    'ETORO_USER_KEY',
}


def build_run_id(started_at: datetime | None = None) -> str:
    actual_started_at = started_at or datetime.now(timezone.utc)
    return actual_started_at.strftime('run_%Y%m%dT%H%M%S_%fZ')


def run_artifact_path(base_path: str, run_id: str) -> str:
    path = Path(base_path)
    return str(path.parent / 'runs' / run_id / path.name)


def resolve_git_commit() -> str | None:
    for variable_name in ('GIT_COMMIT', 'GITHUB_SHA', 'SOURCE_VERSION'):
        value = os.getenv(variable_name)
        if value and value.strip().lower() not in {'unknown', 'local'}:
            return value.strip()

    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    commit = result.stdout.strip()
    return commit or None


def resolve_code_fingerprint(
    source_root: str | Path | None = None,
) -> str | None:
    root = (
        Path(source_root)
        if source_root is not None
        else Path(__file__).resolve().parents[1]
    )
    source_files = sorted(
        path for path in root.rglob('*.py') if path.is_file()
    )
    if not source_files:
        return None

    digest = hashlib.sha256()
    for source_file in source_files:
        relative_path = source_file.relative_to(root).as_posix()
        digest.update(relative_path.encode('utf-8'))
        digest.update(b'\0')
        digest.update(source_file.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def build_run_manifest(
    *,
    settings: Settings,
    strategy_profile: Any,
    instrument_registry: InstrumentRegistry,
    symbols: list[str],
    run_id: str,
    started_at: datetime,
    manifest_path: str | None = None,
    summary_path: str | None = None,
) -> dict[str, Any]:
    symbol_profiles = {
        symbol: instrument_registry.resolve(symbol)
        for symbol in symbols
    }
    benchmark_symbols = {
        asset_class.value: list(configured_symbols)
        for asset_class, configured_symbols
        in settings.benchmark_symbols_by_asset_class().items()
    }
    actual_manifest_path = manifest_path or settings.run_manifest_path
    actual_summary_path = summary_path or settings.daily_summary_path
    return {
        'schema_version': 5,
        'run_id': run_id,
        'status': 'running',
        'started_at': started_at,
        'ended_at': None,
        'code': {
            'git_commit': resolve_git_commit(),
            'source_sha256': resolve_code_fingerprint(),
            'python_version': platform.python_version(),
        },
        'models': {
            'market_context': MARKET_CONTEXT_VERSION,
            'multi_timeframe': MULTI_TIMEFRAME_MODEL_VERSION,
            'entry_decision': ENTRY_DECISION_MODEL_VERSION,
            'tp_probability': TP_PROBABILITY_MODEL_VERSION,
        },
        'strategy': {
            'name': 'TrendStrategy',
            'profile': strategy_profile.name,
            'profile_config': strategy_profile,
        },
        'runtime': {
            'watchlist': symbols,
            'context_benchmarks': benchmark_symbols,
            'symbol_profiles': symbol_profiles,
            'settings': sanitized_settings_snapshot(settings),
            'multi_timeframe': {
                'base_timeframe_seconds': BASE_TIMEFRAME.value,
                'supported_timeframes_seconds': [
                    timeframe.value for timeframe in SUPPORTED_TIMEFRAMES
                ],
                'supported_timeframes': [
                    timeframe.name.lower()
                    for timeframe in SUPPORTED_TIMEFRAMES
                ],
                'poll_interval_seconds': settings.poll_interval_seconds,
                'expected_sampling_quality': expected_sampling_quality(
                    settings.poll_interval_seconds
                ),
                'config_by_symbol': {
                    symbol: instrument_registry.config_for(
                        symbol
                    ).multi_timeframe
                    for symbol in symbols
                },
            },
        },
        'analysis_sources': {
            'run_id': run_id,
            'market_stream': settings.market_log_path,
            'candle_stream': settings.candle_journal_path,
            'trade_stream': settings.journal_path,
            'error_stream': settings.errors_journal_path,
            'raw_market_retained': True,
            'raw_candles_retained': True,
            'multi_timeframe_bars_retained': True,
            'multi_timeframe_candidate_snapshots_retained': True,
            'candidate_id_enabled': True,
            'pending_lineage_enabled': True,
            'entry_routing_retained': True,
            'analysis_ready_entry_fields': [
                'candidate_id',
                'origin_candidate_id',
                'pending_entry_id',
                'candidate_timestamp',
                'symbol',
                'side',
                'entry_reference_price',
                'effective_stop_loss_percent',
                'effective_take_profit_percent',
                'estimated_total_cost_percent',
                'score',
                'base_score',
                'entry_route_action',
                'entry_route_reason',
                'selection_outcome',
                'selection_reason',
                'break_even_probability',
                'net_expected_value_percent',
                'probability_edge',
            ],
        },
        'files': {
            'manifest': actual_manifest_path,
            'latest_manifest': settings.run_manifest_path,
            'summary': actual_summary_path,
            'latest_summary': settings.daily_summary_path,
            'partial_summary': settings.partial_daily_summary_path,
            'trades': settings.journal_path,
            'errors': settings.errors_journal_path,
            'market': settings.market_log_path,
            'candles': settings.candle_journal_path,
            'debug_decisions': settings.debug_decisions_journal_path,
        },
    }


def sanitized_settings_snapshot(settings: Settings) -> dict[str, Any]:
    values = settings.model_dump(by_alias=True)
    return {
        key: value
        for key, value in values.items()
        if key not in _SENSITIVE_SETTINGS
    }


def write_run_manifest(path: str, manifest: dict[str, Any]) -> None:
    _write_json_atomically(Path(path), manifest)


def finalize_run_manifest(
    path: str,
    *,
    ended_at: datetime | None = None,
    status: str = 'completed',
    summary: dict[str, Any] | None = None,
) -> None:
    manifest_path = Path(path)
    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['status'] = status
    manifest['ended_at'] = ended_at or datetime.now(timezone.utc)
    if summary is not None:
        manifest['result'] = {
            'market_snapshots': summary.get(
                'market_data',
                {},
            ).get('snapshots', 0),
            'market_data_rejected': summary.get(
                'market_data',
                {},
            ).get('rejected', 0),
            'market_data_quarantined': summary.get(
                'market_data',
                {},
            ).get('quarantined', 0),
            'candles_closed': summary.get(
                'market_data',
                {},
            ).get('candles_closed', 0),
            'timeframe_bars_closed': summary.get(
                'multi_timeframe',
                {},
            ).get('closed_total', 0),
            'timeframe_bars_incomplete': summary.get(
                'multi_timeframe',
                {},
            ).get('incomplete_total', 0),
            'candle_gaps': summary.get(
                'multi_timeframe',
                {},
            ).get('gap_total', 0),
            'ready_for_selection': summary.get(
                'entry_routing',
                {},
            ).get('ready_for_selection', 0),
            'wait_for_retest': summary.get(
                'entry_routing',
                {},
            ).get('wait_for_retest', 0),
            'skip': summary.get(
                'entry_routing',
                {},
            ).get('skip', 0),
            'orders_submitted': summary.get(
                'orders',
                {},
            ).get('submitted', 0),
            'positions_opened': summary.get(
                'positions',
                {},
            ).get('opened', 0),
            'positions_closed': summary.get(
                'positions',
                {},
            ).get('closed', 0),
            'errors': summary.get('errors', {}).get('total', 0),
        }
    _write_json_atomically(manifest_path, manifest)


def _write_json_atomically(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + '.tmp')
    temporary_path.write_text(
        json.dumps(
            serialize_value(value),
            ensure_ascii=False,
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )
    temporary_path.replace(path)
