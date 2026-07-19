import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


class ProbeRecorder:
    def __init__(
        self,
        output_directory: Path,
        *,
        echo_events_to_console: bool = True,
    ):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.echo_events_to_console = echo_events_to_console
        self._lock = Lock()

    def append(self, stream: str, record: dict[str, Any]) -> None:
        path = self.output_directory / f'{stream}.jsonl'
        serialized = json.dumps(
            record,
            ensure_ascii=False,
            default=_json_default,
            separators=(',', ':'),
        )
        with self._lock, path.open('a', encoding='utf-8') as file:
            file.write(f'{serialized}\n')
            if stream == 'events' and self.echo_events_to_console:
                print(f'[market-data-probe] {serialized}', flush=True)

    def write_json(self, filename: str, payload: dict[str, Any]) -> None:
        path = self.output_directory / filename
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
        with self._lock, path.open('w', encoding='utf-8') as file:
            file.write(f'{serialized}\n')


def _json_default(value: object):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f'Object is not JSON serializable: {type(value).__name__}')
