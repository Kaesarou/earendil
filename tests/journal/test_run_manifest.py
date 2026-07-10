from datetime import datetime, timezone

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.run_manifest import (
    build_run_manifest,
    resolve_code_fingerprint,
    run_artifact_path,
    sanitized_settings_snapshot,
)
from app.strategies.strategy import strategy_profile_from_name


def test_run_manifest_captures_replay_configuration_without_broker_secrets():
    settings = Settings(
        WATCHLIST='AAPL',
        EQUITY_US_SYMBOLS='AAPL',
        ETORO_API_KEY='secret-api',
        ETORO_USER_KEY='secret-user',
    )
    profile = strategy_profile_from_name('balanced')
    registry = InstrumentRegistry(
        settings,
        instrument_configs=profile.instrument_configs,
    )
    started_at = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)

    manifest = build_run_manifest(
        settings=settings,
        strategy_profile=profile,
        instrument_registry=registry,
        symbols=['AAPL'],
        run_id='run-test',
        started_at=started_at,
        manifest_path='data/logs/runs/run-test/run_manifest.json',
        summary_path='data/logs/runs/run-test/daily_summary.json',
    )

    snapshot = manifest['runtime']['settings']
    assert 'ETORO_API_KEY' not in snapshot
    assert 'ETORO_USER_KEY' not in snapshot
    assert manifest['strategy']['profile'] == 'balanced'
    assert manifest['runtime']['watchlist'] == ['AAPL']
    assert manifest['replay']['filter_by_run_id'] == 'run-test'
    assert manifest['files']['manifest'].endswith('runs/run-test/run_manifest.json')
    assert manifest['code']['source_sha256']


def test_sanitized_settings_keeps_non_sensitive_replay_values():
    settings = Settings(
        WATCHLIST='AAPL',
        EQUITY_US_SYMBOLS='AAPL',
        CANDLE_TIMEFRAME_SECONDS=300,
    )

    snapshot = sanitized_settings_snapshot(settings)

    assert snapshot['WATCHLIST'] == 'AAPL'
    assert snapshot['CANDLE_TIMEFRAME_SECONDS'] == 300


def test_run_artifact_path_creates_stable_per_run_location():
    assert run_artifact_path('data/logs/daily_summary.json', 'run-123') == (
        'data/logs/runs/run-123/daily_summary.json'
    )


def test_code_fingerprint_changes_when_source_changes(tmp_path):
    source_file = tmp_path / 'module.py'
    source_file.write_text('VALUE = 1\n', encoding='utf-8')
    first_fingerprint = resolve_code_fingerprint(tmp_path)

    source_file.write_text('VALUE = 2\n', encoding='utf-8')
    second_fingerprint = resolve_code_fingerprint(tmp_path)

    assert first_fingerprint
    assert second_fingerprint
    assert first_fingerprint != second_fingerprint
