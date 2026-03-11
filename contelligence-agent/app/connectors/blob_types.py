"""Shared blob storage data classes.

Used by both ``BlobConnectorAdapter`` (Azure) and ``LocalBlobConnectorAdapter``
(local filesystem) so that consumer code can import from a single location.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BlobInfo:
    name: str
    size: int
    content_type: str | None


@dataclass
class BlobProperties:
    name: str
    size: int
    content_type: str | None
    metadata: dict[str, str]
