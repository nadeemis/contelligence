"""Cosmos DB provisioning — create database and containers idempotently.

Called during application startup to ensure the ``contelligence-agent`` database
and its three containers (``sessions``, ``conversation``, ``outputs``) exist
with the correct partition keys, indexing policies, and composite indexes.

All ``create_*_if_not_exists`` calls are idempotent — safe to call on every
application start with no side-effects on existing data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from azure.cosmos import PartitionKey

if TYPE_CHECKING:
    from azure.cosmos.aio import CosmosClient

logger = logging.getLogger(f"contelligence-agent.{__name__}")

async def provision_cosmos_db(
    cosmos_client: "CosmosClient",
    database_name: str = "contelligence-agent",
) -> None:
    """Create the database and containers for Phase 2 session persistence.

    Parameters
    ----------
    cosmos_client:
        An initialised async ``CosmosClient`` instance.
    database_name:
        Name of the database to create (default ``contelligence-agent``).

    Container details:
    - **sessions** (pk ``/id``) — one document per session.
      Composite index on ``(status ASC, created_at DESC)`` for
      ``list_sessions()`` queries.
    - **conversation** (pk ``/session_id``) — conversation turns.
      Composite index on ``(session_id ASC, sequence ASC)`` for
      ordered retrieval.
    - **outputs** (pk ``/session_id``) — output artifacts.
      Default indexing — queries always filter by partition key.
    """
    logger.info("Provisioning Cosmos DB database '%s'...", database_name)

    database = await cosmos_client.create_database_if_not_exists(id=database_name)

    logger.info(f"Database '{database_name}' ready. Ensuring containers exist...")
    
    # ------------------------------------------------------------------
    # sessions container — partition key: /id
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="sessions",
        partition_key=PartitionKey(path="/id"),
        indexing_policy={
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": '/"_etag"/?'}],
            "compositeIndexes": [
                [
                    {"path": "/status", "order": "ascending"},
                    {"path": "/created_at", "order": "descending"},
                ],
            ],
        },
    )
    logger.info("Container 'sessions' ready (pk: /id).")

    # ------------------------------------------------------------------
    # conversation container — partition key: /session_id
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="conversation",
        partition_key=PartitionKey(path="/session_id"),
        indexing_policy={
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": '/"_etag"/?'}],
            "compositeIndexes": [
                [
                    {"path": "/session_id", "order": "ascending"},
                    {"path": "/sequence", "order": "ascending"},
                ],
            ],
        },
    )
    logger.info("Container 'conversation' ready (pk: /session_id).")
    
    # ------------------------------------------------------------------
    # events container — partition key: /session_id
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="events",
        partition_key=PartitionKey(path="/session_id"),
        indexing_policy={
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": '/"_etag"/?'}],
            "compositeIndexes": [
                [
                    {"path": "/session_id", "order": "ascending"},
                    {"path": "/timestamp", "order": "ascending"},
                ],
            ],
        },
    )
    logger.info("Container 'events' ready (pk: /session_id).")

    # ------------------------------------------------------------------
    # outputs container — partition key: /session_id
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="outputs",
        partition_key=PartitionKey(path="/session_id"),
    )
    logger.info("Container 'outputs' ready (pk: /session_id).")

    # ------------------------------------------------------------------
    # extraction-cache container (TTL-enabled)
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="extraction-cache",
        partition_key=PartitionKey(path="/pk"),
        default_ttl=604800,  # 7 days default TTL — documents specify their own
    )
    logger.info("Container 'extraction-cache' ready (pk: /pk, TTL enabled).")

    # ------------------------------------------------------------------
    # scheduler-locks container
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="scheduler-locks",
        partition_key=PartitionKey(path="/id"),
    )
    logger.info("Container 'scheduler-locks' ready (pk: /id).")

    # ------------------------------------------------------------------
    # schedules container (pk: /id)
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="schedules",
        partition_key=PartitionKey(path="/id"),
        indexing_policy={
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": '/"_etag"/?'}],
            "compositeIndexes": [
                [
                    {"path": "/status", "order": "ascending"},
                    {"path": "/created_at", "order": "descending"},
                ],
                [
                    {"path": "/trigger/type", "order": "ascending"},
                    {"path": "/next_run_at", "order": "ascending"},
                ],
            ],
        },
    )
    logger.info("Container 'schedules' ready (pk: /id).")

    # ------------------------------------------------------------------
    # schedule-runs container (pk: /schedule_id)
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="schedule-runs",
        partition_key=PartitionKey(path="/schedule_id"),
        indexing_policy={
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": '/"_etag"/?'}],
            "compositeIndexes": [
                [
                    {"path": "/schedule_id", "order": "ascending"},
                    {"path": "/triggered_at", "order": "descending"},
                ],
            ],
        },
    )
    logger.info("Container 'schedule-runs' ready (pk: /schedule_id).")

    # ------------------------------------------------------------------
    # Custom Agent Management — agents container (pk: /id)
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="agents",
        partition_key=PartitionKey(path="/id"),
        indexing_policy={
            "includedPaths": [
                {"path": "/"},
                {"path": "/status/?"},
                {"path": "/source/?"},
                {"path": "/tags/[]/?"},
                {"path": "/created_at/?"},
                {"path": "/display_name/?"},
            ],
            "excludedPaths": [
                {"path": "/prompt/*"},
                {"path": '/"_etag"/?'},
            ],
            "compositeIndexes": [
                [
                    {"path": "/status", "order": "ascending"},
                    {"path": "/created_at", "order": "descending"},
                ],
                [
                    {"path": "/source", "order": "ascending"},
                    {"path": "/display_name", "order": "ascending"},
                ],
            ],
        },
    )
    logger.info("Container 'agents' ready (pk: /id).")

    # ------------------------------------------------------------------
    # Skills Integration — skills container (pk: /partition_key)
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="skills",
        partition_key=PartitionKey(path="/partition_key"),
        indexing_policy={
            "includedPaths": [
                {"path": "/"},
                {"path": "/status/?"},
                {"path": "/source/?"},
                {"path": "/tags/[]/?"},
                {"path": "/name/?"},
                {"path": "/created_at/?"},
            ],
            "excludedPaths": [
                {"path": "/instructions/*"},
                {"path": '/"_etag"/?'},
            ],
            "compositeIndexes": [
                [
                    {"path": "/status", "order": "ascending"},
                    {"path": "/name", "order": "ascending"},
                ],
                [
                    {"path": "/source", "order": "ascending"},
                    {"path": "/created_at", "order": "descending"},
                ],
            ],
        },
    )
    logger.info("Container 'skills' ready (pk: /partition_key).")

    # ------------------------------------------------------------------
    # Prompt management — prompts container (pk: /id)
    # ------------------------------------------------------------------
    await database.create_container_if_not_exists(
        id="prompts",
        partition_key=PartitionKey(path="/id"),
        indexing_policy={
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [
                {"path": "/content/*"},
                {"path": '/"_etag"/?'},
            ],
        },
    )
    logger.info("Container 'prompts' ready (pk: /id).")

    logger.info("Cosmos DB provisioning complete.")
