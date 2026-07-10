import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.serialization import serialize_value

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
        if value:
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
    actual_manifest_path = manifest_path or settings.run_manifest_path
    actual_summary_path = summary_path or settings.daily_summary_path
    replay_report_path = run_artifact_path(settings.replay_report_path, run_id)
    return {
        'schema_version': 1,
        'run_id': run_id,
        'status': 'running',
        'started_at': started_at,
        'ended_at': None,
        'code': {
            'git_commit': resolve_git_commit(),
            'python_version': platform.python_version(),
        },
        'strategy': {
            'name': 'TrendStrategy',
            'profile': strategy_profile.name,
            'profile_config': strategy_profile,
        },
        'runtime': {
            'watchlist': symbols,
            'symbol_profiles': symbol_profiles,
            'settings': sanitized_settings_snapshot(settings),
        },
        'replay': {
            'source_of_truth': 'market',
            'requires_contiguous_sequences': True,
            'market_stream': settings.market_log_path,
            'candle_stream': settings.candle_journal_path,
            'trade_stream': settings.journal_path,
            'comparison_baseline': settings.journal_path,
            'filter_by_run_id': run_id,
        },
        'files': {
            'manifest': actual_manifest_path,
            'latest_manifest': settings.run_manifest_path,
            'summary': actual_summary_path,
            'latest_summary': settings.daily_summary_path,
            'replay_report': replay_report_path,
            'latest_replay_report': settings.replay_report_path,
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
            'market_snapshots': summary.get('market_data', {}).get('snapshots', 0),
            'candles_closed': summary.get('market_data', {}).get('candles_closed', 0),
            'orders_submitted': summary.get('orders', {}).get('submitted', 0),
            'positions_opened': summary.get('positions', {}).get('opened', 0),
            'positions_closed': summary.get('positions', {}).get('closed', 0),
            'errors': summary.get('errors', {}).get('total', 0),
        }
    _write_json_atomically(manifest_path, manifest)


def _write_json_atomically(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + '.tmp')
    temporary_path.write_text(
        json.dumps(serialize_value(value), ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    temporary_path.replace(path)
