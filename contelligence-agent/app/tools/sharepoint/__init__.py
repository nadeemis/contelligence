"""SharePoint REST API v1 tools for document library and file operations."""

from __future__ import annotations

from .list_document_libraries import list_document_libraries
from .list_items import list_items
from .download_file import download_file
from .browser_download_file import browser_download_file
from .browser_list_document_libraries import browser_list_document_libraries
from .browser_list_items import browser_list_items

SHAREPOINT_TOOLS = [
    list_document_libraries,
    list_items,
    download_file,
    browser_download_file,
    browser_list_document_libraries,
    browser_list_items,
]
