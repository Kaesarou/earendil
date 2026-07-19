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


def test_probe_validation_requires_websocket_authentication_and_rates():
    summary = {
        'websocket': {'authentication_successes': 0},
        'rates': {'rest_rate': {'BTC': {'observations': 30}}},
    }

    assert run_etoro_market_data_probe._probe_validation_errors(summary) == [
        'no successful WebSocket authentication',
        'no WebSocket market-rate observations',
    ]


def test_probe_validation_accepts_websocket_observations():
    summary = {
        'websocket': {'authentication_successes': 1},
        'rates': {
            'websocket_rate': {
                'BTC': {'observations': 1},
            }
        },
    }

    assert run_etoro_market_data_probe._probe_validation_errors(summary) == []
