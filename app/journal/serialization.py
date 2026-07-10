import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any


def serialize_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return serialize_value(asdict(value))
    if hasattr(value, '_asdict'):
        return serialize_value(value._asdict())
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, MappingProxyType):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, '__dict__') and not isinstance(value, type):
        return serialize_value(vars(value))
    return value
