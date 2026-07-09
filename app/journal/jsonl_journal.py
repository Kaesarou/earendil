import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from app.journal.serialization import serialize_value

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
                'payload': serialize_value(payload),
            }
            with self._open_append() as file:
                file.write(json.dumps(record, ensure_ascii=False) + '\n')

        except Exception as exc:
            logger.exception(
                'Journal write failed | path=%s | event_type=%s | error=%s',
                self.path,
                event_type,
                exc,
            )

    def _open_append(self) -> TextIO:
        if self.path.suffix == '.gz':
            return gzip.open(self.path, 'at', encoding='utf-8')
        return self.path.open('a', encoding='utf-8')

    def _serialize(self, value: Any) -> Any:
        return serialize_value(value)
