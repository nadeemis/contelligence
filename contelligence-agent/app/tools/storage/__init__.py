"""Storage tools for Azure Blob, AI Search, and Cosmos DB."""

from __future__ import annotations

from .read_blob import read_blob
from .write_blob import write_blob
from .upload_to_search import upload_to_search
from .query_search_index import query_search_index
from .upsert_cosmos import upsert_cosmos
from .query_cosmos import query_cosmos

STORAGE_TOOLS = [
    read_blob,
    write_blob,
    upload_to_search,
    query_search_index,
    upsert_cosmos,
    query_cosmos,
]
