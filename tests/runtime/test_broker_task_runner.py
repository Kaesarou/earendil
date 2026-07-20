from threading import Event

from app.runtime.broker_task_runner import BrokerTaskRunner


def test_broker_task_runner_returns_success_and_error_completions():
    runner = BrokerTaskRunner()
    gate = Event()

    runner.submit(
        kind='success',
        task_id='success-1',
        context={'value': 1},
        operation=lambda: gate.wait(1) or 42,
    )
    gate.set()

    completions = []
    for _ in range(100):
        completions.extend(runner.drain())
        if completions:
            break
    runner.close(wait=True)

    assert len(completions) == 1
    assert completions[0].kind == 'success'
    assert completions[0].value == 42
    assert completions[0].error is None


def test_broker_task_runner_surfaces_operation_error():
    runner = BrokerTaskRunner()

    def fail():
        raise RuntimeError('boom')

    runner.submit(kind='failure', task_id='failure-1', operation=fail)
    runner.close(wait=True)
    completions = runner.drain()

    assert len(completions) == 1
    assert completions[0].kind == 'failure'
    assert isinstance(completions[0].error, RuntimeError)
    assert str(completions[0].error) == 'boom'
