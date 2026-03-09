"""Tool for refreshing a Power BI dataset."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

from ._client import powerbi_request

logger = logging.getLogger(__name__)


class RefreshDatasetParams(BaseModel):
    """Parameters for the refresh_dataset tool."""

    dataset_id: str = Field(
        ...,
        description="The Power BI dataset (semantic model) ID to refresh.",
    )
    workspace_id: str | None = Field(
        None,
        description=(
            "Power BI workspace (group) ID. Uses the configured default "
            "when omitted."
        ),
    )
    notify_option: str = Field(
        "NoNotification",
        description=(
            "Notification preference after refresh completes. "
            "Options: 'NoNotification', 'MailOnFailure', 'MailOnCompletion'."
        ),
    )


@define_tool(
    name="powerbi_refresh_dataset",
    description=(
        "Trigger a refresh of a Power BI dataset (semantic model). "
        "Use this to ensure report data is up-to-date before querying."
    ),
    parameters_model=RefreshDatasetParams,
)
async def refresh_dataset(
    params: RefreshDatasetParams, context: dict,
) -> dict[str, Any]:
    """Trigger a dataset refresh."""
    try:
        body = {"notifyOption": params.notify_option}

        await powerbi_request(
            context,
            f"datasets/{params.dataset_id}/refreshes",
            method="POST",
            json_body=body,
            workspace_id=params.workspace_id,
        )

        return {
            "dataset_id": params.dataset_id,
            "status": "refresh_triggered",
            "notify_option": params.notify_option,
        }

    except Exception as exc:
        logger.exception(
            "Failed to trigger refresh for dataset %s", params.dataset_id,
        )
        return {
            "error": str(exc),
            "dataset_id": params.dataset_id,
        }
