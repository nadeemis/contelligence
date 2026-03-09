"""Azure DevOps tools for work item tracking and project information."""

from __future__ import annotations

from .get_work_item import get_work_item
from .list_work_items import list_work_items
from .query_work_items import query_work_items
from .get_iterations import get_iterations
from .get_project import get_project

DEVOPS_TOOLS = [
    get_work_item,
    list_work_items,
    query_work_items,
    get_iterations,
    get_project,
]
