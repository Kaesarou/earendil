from pathlib import Path

from app.journal.run_paths import build_run_journal_paths, rotate_run_journals


def test_run_paths_are_compressed_and_isolated(tmp_path):
    paths = build_run_journal_paths(
        journal_path=str(tmp_path / 'logs' / 'trades.jsonl'),
        run_id='run-123',
    )

    assert paths.root == tmp_path / 'logs' / 'runs' / 'run-123'
    assert paths.trades.name == 'trades.jsonl.gz'
    assert paths.market.name == 'market.jsonl.gz'
    assert paths.candles.name == 'candles.jsonl.gz'
    assert paths.errors.name == 'errors.jsonl.gz'
    assert paths.root.exists()


def test_run_rotation_keeps_current_and_newest_runs(tmp_path):
    runs_root = tmp_path / 'runs'
    current = runs_root / 'run-current'
    current.mkdir(parents=True)
    old = runs_root / 'run-old'
    old.mkdir()
    recent = runs_root / 'run-recent'
    recent.mkdir()
    (old / 'marker').write_text('old', encoding='utf-8')
    (recent / 'marker').write_text('recent', encoding='utf-8')
    old.touch()
    recent.touch()
    old_time = 1_000_000_000
    recent_time = old_time + 100
    import os

    os.utime(old, (old_time, old_time))
    os.utime(recent, (recent_time, recent_time))

    removed = rotate_run_journals(
        runs_root=runs_root,
        max_runs=2,
        current_run_id='run-current',
    )

    assert removed == ('run-old',)
    assert current.exists()
    assert recent.exists()
    assert not old.exists()
