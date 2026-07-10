import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, TextIO

from app.market.models import MarketSnapshot


class ReplayIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class JournalRecord:
    run_id: str | None
    stream: str
    sequence: int | None
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class MarketReplayEvent:
    sequence: int
    loop_id: int | None
    snapshot: MarketSnapshot


class ReplayDataset:
    def __init__(self, manifest_path: str):
        self.manifest_path = Path(manifest_path)
        self.manifest = json.loads(self.manifest_path.read_text(encoding='utf-8'))
        self.run_id = self.manifest.get('run_id')
        if not self.run_id:
            raise ReplayIntegrityError('Run manifest does not contain a run_id.')

    def market_records(self) -> list[JournalRecord]:
        path = self._resolve_file('market')
        return list(read_journal_records(path, run_id=self.run_id, validate_sequences=True))

    def trade_records(self) -> list[JournalRecord]:
        path = self._resolve_file('trades')
        return list(read_journal_records(path, run_id=self.run_id, validate_sequences=True))

    def candle_records(self) -> list[JournalRecord]:
        path = self._resolve_file('candles')
        return list(read_journal_records(path, run_id=self.run_id, validate_sequences=True))

    def market_events(self) -> list[MarketReplayEvent]:
        events: list[MarketReplayEvent] = []
        for record in self.market_records():
            if record.event_type != 'market_snapshot':
                continue
            snapshot_payload = record.payload.get('snapshot')
            if not isinstance(snapshot_payload, dict):
                raise ReplayIntegrityError(
                    f'Market record sequence {record.sequence} has no snapshot payload.'
                )
            if record.sequence is None:
                raise ReplayIntegrityError('Market records must have a sequence.')
            events.append(
                MarketReplayEvent(
                    sequence=record.sequence,
                    loop_id=_optional_int(record.payload.get('loop_id')),
                    snapshot=_market_snapshot_from_dict(snapshot_payload),
                )
            )
        return events

    def validate(self) -> dict[str, Any]:
        market_records = self.market_records()
        candle_records = self.candle_records()
        trade_records = self.trade_records()
        return {
            'run_id': self.run_id,
            'market_records': len(market_records),
            'candle_records': len(candle_records),
            'trade_records': len(trade_records),
            'market_sequence_contiguous': True,
            'candle_sequence_contiguous': True,
            'trade_sequence_contiguous': True,
        }

    def _resolve_file(self, key: str) -> Path:
        raw_path = self.manifest.get('files', {}).get(key)
        if not raw_path:
            raise ReplayIntegrityError(f'Manifest does not define the {key} file.')

        path = Path(raw_path)
        if path.exists():
            return path

        relative_to_manifest = self.manifest_path.parent / path.name
        if relative_to_manifest.exists():
            return relative_to_manifest

        raise ReplayIntegrityError(f'Replay file not found: {raw_path}')


def read_journal_records(
    path: str | Path,
    *,
    run_id: str | None = None,
    validate_sequences: bool = True,
) -> Iterator[JournalRecord]:
    expected_sequence = 1
    matched_records = 0
    with _open_text(Path(path)) as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                raw_record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReplayIntegrityError(
                    f'Invalid JSON in {path} at line {line_number}: {exc}'
                ) from exc

            record_run_id = raw_record.get('run_id')
            if run_id is not None and record_run_id != run_id:
                continue

            sequence = _optional_int(raw_record.get('sequence'))
            if validate_sequences:
                if sequence is None:
                    raise ReplayIntegrityError(
                        f'Missing sequence in {path} for run {run_id or record_run_id}.'
                    )
                if sequence != expected_sequence:
                    raise ReplayIntegrityError(
                        f'Non-contiguous sequence in {path}: expected {expected_sequence}, got {sequence}.'
                    )
                expected_sequence += 1

            matched_records += 1
            yield JournalRecord(
                run_id=record_run_id,
                stream=str(raw_record.get('stream') or Path(path).name),
                sequence=sequence,
                timestamp=datetime.fromisoformat(raw_record['timestamp']),
                event_type=str(raw_record['event_type']),
                payload=dict(raw_record.get('payload') or {}),
            )

    if run_id is not None and matched_records == 0:
        raise ReplayIntegrityError(f'No records found for run_id={run_id} in {path}.')


def _open_text(path: Path) -> TextIO:
    if path.suffix == '.gz':
        return gzip.open(path, 'rt', encoding='utf-8')
    return path.open('r', encoding='utf-8')


def _market_snapshot_from_dict(value: dict[str, Any]) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=str(value['symbol']),
        bid=float(value['bid']),
        ask=float(value['ask']),
        last=float(value['last']),
        timestamp=datetime.fromisoformat(str(value['timestamp'])),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
