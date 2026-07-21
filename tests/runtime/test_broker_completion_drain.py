from types import SimpleNamespace

from app.runtime.market_data_runtime import EventDrivenMarketRuntime


def test_runtime_routes_broker_completions_on_main_loop():
    first = object()
    second = object()
    candidate_calls = []
    broker_calls = []
    runtime = object.__new__(EventDrivenMarketRuntime)
    runtime.broker_task_runner = SimpleNamespace(
        drain=lambda: [first, second]
    )
    runtime.candidate_execution = SimpleNamespace(
        handle_completion=lambda completion, now: (
            candidate_calls.append((completion, now)) or completion is first
        )
    )
    runtime.broker_operations = SimpleNamespace(
        handle_completion=lambda completion, now, latest_snapshots: (
            broker_calls.append((completion, now, latest_snapshots))
        )
    )
    runtime.latest_snapshots = {'BTC': object()}
    now = object()

    runtime._drain_broker_completions(now)

    assert candidate_calls == [(first, now), (second, now)]
    assert broker_calls == [(second, now, runtime.latest_snapshots)]
