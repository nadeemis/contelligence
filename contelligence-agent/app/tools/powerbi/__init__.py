"""Power BI tools for querying datasets via the XMLA-backed REST API."""

from __future__ import annotations

from .execute_dax_query import execute_dax_query
from .get_dataset_tables import get_dataset_tables
from .list_datasets import list_datasets

POWERBI_TOOLS = [
    execute_dax_query,
    get_dataset_tables,
    list_datasets,
]
