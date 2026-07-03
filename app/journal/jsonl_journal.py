import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JsonlJournal:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, payload: dict[str, Any]) -> None:

        try:
            record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'event_type': event_type,
                'payload': self._serialize(payload),
            }
            with self.path.open('a', encoding='utf-8') as file:
                file.write(json.dumps(record, ensure_ascii=False) + '\n')

        except Exception as exc:
            logger.exception(
                'Journal write failed | path=%s | event_type=%s | error=%s',
                self.path,
                event_type,
                exc,
            )

    def _serialize(self, value: Any) -> Any:
        if is_dataclass(value) and not isinstance(value, type):
            return self._serialize(asdict(value))
        if isinstance(value, dict):
            return {key: self._serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return value
