from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from queue import SimpleQueue
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


@dataclass(frozen=True)
class BrokerTaskCompletion:
    task_id: str
    kind: str
    context: Any
    value: Any = None
    error: Exception | None = None


class BrokerTaskRunner:
    """Run blocking broker work outside the market-data consumer.

    A single worker intentionally serializes eToro calls. This preserves request
    ordering and avoids turning the worker into a hidden source of request bursts.
    Runtime state is never mutated in the worker: callers drain completions and
    apply them from the main event loop.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix='goblin-broker',
        )
        self._pending: dict[str, tuple[str, Any, Future]] = {}
        self._completed: SimpleQueue[BrokerTaskCompletion] = SimpleQueue()
        self._lock = Lock()
        self._closed = False

    def submit(
        self,
        *,
        kind: str,
        operation: Callable[[], Any],
        context: Any = None,
        task_id: str | None = None,
    ) -> str:
        identifier = task_id or f'{kind}:{uuid4()}'
        with self._lock:
            if self._closed:
                raise RuntimeError('Broker task runner is closed.')
            if identifier in self._pending:
                raise ValueError(f'Duplicate broker task id: {identifier}')
            future = self._executor.submit(operation)
            self._pending[identifier] = (kind, context, future)
        future.add_done_callback(
            lambda completed, current_id=identifier: self._complete(
                current_id,
                completed,
            )
        )
        return identifier

    def has_pending_kind(self, kind: str) -> bool:
        with self._lock:
            return any(item[0] == kind for item in self._pending.values())

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def drain(self) -> list[BrokerTaskCompletion]:
        completions: list[BrokerTaskCompletion] = []
        while not self._completed.empty():
            completions.append(self._completed.get())
        return completions

    def close(self, *, wait: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _complete(self, task_id: str, future: Future) -> None:
        with self._lock:
            pending = self._pending.pop(task_id, None)
        if pending is None:
            return
        kind, context, _ = pending
        try:
            value = future.result()
        except Exception as exc:  # noqa: BLE001 - propagated as structured result
            self._completed.put(
                BrokerTaskCompletion(
                    task_id=task_id,
                    kind=kind,
                    context=context,
                    error=exc,
                )
            )
            return
        self._completed.put(
            BrokerTaskCompletion(
                task_id=task_id,
                kind=kind,
                context=context,
                value=value,
            )
        )
