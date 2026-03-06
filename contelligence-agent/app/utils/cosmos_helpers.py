"""Cosmos DB serialization helpers.

Cosmos DB expects datetime values as ISO 8601 strings, not native
``datetime`` objects.  The ``to_cosmos_dict`` function handles the
recursive conversion for any Pydantic model before upserting.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


def to_cosmos_dict(model: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic model to a Cosmos-friendly dict.

    Converts ``datetime`` fields to ISO 8601 strings and ``Enum`` members
    to their values, recursively through nested dicts and lists.
    """
    data = model.model_dump()
    return _convert_values(data)


def _convert_values(obj: Any) -> Any:
    """Recursively convert non-serializable types for Cosmos DB."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _convert_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_values(i) for i in obj]
    return obj
