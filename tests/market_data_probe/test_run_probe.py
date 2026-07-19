from scripts import run_etoro_market_data_probe


def test_source_commit_prefers_container_environment(monkeypatch):
    monkeypatch.setenv('GIT_COMMIT', 'container-commit')

    def fail_if_called(*args, **kwargs):
        raise AssertionError('git must not be called when GIT_COMMIT is set')

    monkeypatch.setattr(
        run_etoro_market_data_probe.subprocess,
        'run',
        fail_if_called,
    )

    assert run_etoro_market_data_probe._source_commit() == 'container-commit'


def test_source_commit_tolerates_missing_git(monkeypatch):
    for variable_name in ('GIT_COMMIT', 'GITHUB_SHA', 'SOURCE_VERSION'):
        monkeypatch.delenv(variable_name, raising=False)

    def missing_git(*args, **kwargs):
        raise FileNotFoundError('git')

    monkeypatch.setattr(
        run_etoro_market_data_probe.subprocess,
        'run',
        missing_git,
    )

    assert run_etoro_market_data_probe._source_commit() is None
