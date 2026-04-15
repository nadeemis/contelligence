"""SQLite shim that mimics the Azure Cosmos DB container client API.

Allows SessionStore, AgentStore, ScheduleStore, and SkillStore to work
without code changes by providing the same interface:
    client.get_database_client(name).get_container_client(name)

Each Cosmos container maps to a SQLite table with three columns:
    id TEXT PRIMARY KEY, partition_key TEXT, data TEXT (JSON document)

All document fields are stored inside the ``data`` JSON blob.  The ``id``
and ``partition_key`` columns are extracted at write time for efficient
lookups.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, AsyncIterator

import aiosqlite

logger = logging.getLogger(f"contelligence-agent.{__name__}")


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_session
    ON conversation(partition_key);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session
    ON events(partition_key);

CREATE TABLE IF NOT EXISTS outputs (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outputs_session
    ON outputs(partition_key);

CREATE TABLE IF NOT EXISTS "extraction-cache" (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "scheduler-locks" (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "schedule-runs" (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule
    ON "schedule-runs"(partition_key);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "user-preferences" (
    id TEXT PRIMARY KEY,
    partition_key TEXT NOT NULL,
    data TEXT NOT NULL
);
"""

# Mapping from Cosmos container names to the partition key path used in Cosmos.
# This is needed to extract the partition_key value from a document.
_PARTITION_KEY_PATHS: dict[str, str] = {
    "sessions": "/id",
    "conversation": "/session_id",
    "events": "/session_id",
    "outputs": "/session_id",
    "extraction-cache": "/pk",
    "scheduler-locks": "/id",
    "schedules": "/id",
    "schedule-runs": "/schedule_id",
    "agents": "/id",
    "skills": "/partition_key",
    "prompts": "/id",
    "user-preferences": "/user_id",
}


def _extract_partition_key(table: str, doc: dict[str, Any]) -> str:
    """Extract the partition key value from a document based on the table's known pk path."""
    pk_path = _PARTITION_KEY_PATHS.get(table, "/id")
    field = pk_path.lstrip("/")
    return str(doc.get(field, doc.get("id", "")))


# ---------------------------------------------------------------------------
# SQLiteContainerClient — mimics azure.cosmos.aio.ContainerProxy
# ---------------------------------------------------------------------------


def _synthetic_etag(data_json: str) -> str:
    """Generate a deterministic ETag from serialized document content."""
    return hashlib.md5(data_json.encode()).hexdigest()  # noqa: S324


class SQLiteContainerClient:
    """Mimics azure.cosmos.aio.ContainerProxy for a single SQLite table."""

    def __init__(self, db_path: str, table: str) -> None:
        self._db_path = db_path
        self._table = table

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self._db_path)
        await db.execute("PRAGMA journal_mode=WAL")
        return db

    # ── upsert_item ──────────────────────────────────────────

    async def upsert_item(self, body: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        doc_id = body.get("id", "")
        pk = _extract_partition_key(self._table, body)
        data_json = json.dumps(body, default=str)

        db = await self._get_db()
        try:
            await db.execute(
                f'INSERT OR REPLACE INTO "{self._table}" (id, partition_key, data) VALUES (?, ?, ?)',
                (doc_id, pk, data_json),
            )
            await db.commit()
        finally:
            await db.close()

        result = dict(body)
        result["_etag"] = _synthetic_etag(data_json)
        return result

    # ── create_item ──────────────────────────────────────────

    async def create_item(self, body: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        doc_id = body.get("id", "")
        pk = _extract_partition_key(self._table, body)
        data_json = json.dumps(body, default=str)

        db = await self._get_db()
        try:
            # Check if item already exists
            cursor = await db.execute(
                f'SELECT 1 FROM "{self._table}" WHERE id = ?', (doc_id,),
            )
            if await cursor.fetchone():
                from azure.cosmos.exceptions import CosmosResourceExistsError
                raise CosmosResourceExistsError(
                    status_code=409,
                    message=f"Resource with id '{doc_id}' already exists in {self._table}",
                )

            await db.execute(
                f'INSERT INTO "{self._table}" (id, partition_key, data) VALUES (?, ?, ?)',
                (doc_id, pk, data_json),
            )
            await db.commit()
        finally:
            await db.close()

        result = dict(body)
        result["_etag"] = _synthetic_etag(data_json)
        return result

    # ── read_item ────────────────────────────────────────────

    async def read_item(self, item: str, partition_key: str, **kwargs: Any) -> dict[str, Any]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                f'SELECT data FROM "{self._table}" WHERE id = ?', (item,),
            )
            row = await cursor.fetchone()
        finally:
            await db.close()

        if not row:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError
            raise CosmosResourceNotFoundError(
                status_code=404,
                message=f"Resource '{item}' not found in {self._table}",
            )

        doc = json.loads(row[0])
        doc["_etag"] = _synthetic_etag(row[0])
        return doc

    # ── replace_item ─────────────────────────────────────────

    async def replace_item(
        self, item: str, body: dict[str, Any], **kwargs: Any,
    ) -> dict[str, Any]:
        """Replace an existing item (like Cosmos ``replace_item``).

        ``if_match`` / ``if_none_match`` kwargs are accepted but ignored —
        single-user SQLite does not need ETag-based concurrency control.
        """
        doc_id = body.get("id", item)
        pk = _extract_partition_key(self._table, body)
        data_json = json.dumps(body, default=str)

        db = await self._get_db()
        try:
            cursor = await db.execute(
                f'SELECT 1 FROM "{self._table}" WHERE id = ?', (doc_id,),
            )
            if not await cursor.fetchone():
                from azure.cosmos.exceptions import CosmosResourceNotFoundError

                raise CosmosResourceNotFoundError(
                    status_code=404,
                    message=f"Resource '{doc_id}' not found in {self._table}",
                )

            await db.execute(
                f'INSERT OR REPLACE INTO "{self._table}" (id, partition_key, data) VALUES (?, ?, ?)',
                (doc_id, pk, data_json),
            )
            await db.commit()
        finally:
            await db.close()

        result = dict(body)
        result["_etag"] = _synthetic_etag(data_json)
        return result

    # ── delete_item ──────────────────────────────────────────

    async def delete_item(self, item: str, partition_key: str, **kwargs: Any) -> None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                f'SELECT 1 FROM "{self._table}" WHERE id = ?', (item,),
            )
            if not await cursor.fetchone():
                from azure.cosmos.exceptions import CosmosResourceNotFoundError
                raise CosmosResourceNotFoundError(
                    status_code=404,
                    message=f"Resource '{item}' not found in {self._table}",
                )

            await db.execute(
                f'DELETE FROM "{self._table}" WHERE id = ?', (item,),
            )
            await db.commit()
        finally:
            await db.close()

    # ── query_items ──────────────────────────────────────────

    def query_items(
        self,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
        **kwargs: Any,
    ) -> "SQLiteQueryIterable":
        return SQLiteQueryIterable(
            db_path=self._db_path,
            table=self._table,
            cosmos_query=query,
            cosmos_params=parameters,
            partition_key=partition_key,
        )


# ---------------------------------------------------------------------------
# SQLiteQueryIterable — async iterable over query results
# ---------------------------------------------------------------------------


class SQLiteQueryIterable:
    """Async iterable that translates Cosmos SQL queries to SQLite.

    Supports common Cosmos SQL patterns:
    - SELECT * FROM c WHERE ...
    - SELECT TOP N * FROM c WHERE ... ORDER BY ...
    - SELECT c.id FROM c WHERE ...
    - SELECT VALUE COUNT(1) FROM c WHERE ...
    - WHERE c.field = @param with parameterised queries
    - OFFSET N LIMIT M
    - ARRAY_CONTAINS(c.field, @param)
    - Partition-key-scoped queries
    """

    def __init__(
        self,
        db_path: str,
        table: str,
        cosmos_query: str,
        cosmos_params: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> None:
        self._db_path = db_path
        self._table = table
        self._cosmos_query = cosmos_query
        self._cosmos_params = cosmos_params or []
        self._partition_key = partition_key
        self._results: list[Any] | None = None
        self._index = 0

    def __aiter__(self) -> "SQLiteQueryIterable":
        self._results = None
        self._index = 0
        return self

    async def __anext__(self) -> Any:
        if self._results is None:
            self._results = await self._execute()
            self._index = 0

        if self._index >= len(self._results):
            raise StopAsyncIteration

        item = self._results[self._index]
        self._index += 1
        return item

    async def _execute(self) -> list[Any]:
        """Load all matching rows from SQLite and apply Cosmos-style filtering."""
        import re

        query = self._cosmos_query.strip()
        params_map: dict[str, Any] = {
            p["name"]: p["value"] for p in self._cosmos_params
        }

        # Detect VALUE COUNT queries
        is_count = "SELECT VALUE COUNT" in query.upper()

        # Detect field-selection queries (e.g., SELECT c.id FROM c)
        select_field = None
        field_match = re.match(
            r"SELECT\s+c\.(\w+)\s+FROM\s+c", query, re.IGNORECASE,
        )
        if field_match and not is_count:
            select_field = field_match.group(1)

        # Extract TOP N
        top_n = None
        top_match = re.search(r"SELECT\s+TOP\s+(\d+)", query, re.IGNORECASE)
        if top_match:
            top_n = int(top_match.group(1))

        # Extract OFFSET/LIMIT
        offset = 0
        limit = None
        offset_match = re.search(
            r"OFFSET\s+(?:@offset|(\d+))\s+LIMIT\s+(?:@limit|(\d+))",
            query,
            re.IGNORECASE,
        )
        if offset_match:
            offset = int(offset_match.group(1)) if offset_match.group(1) else int(params_map.get("@offset", 0))
            limit = int(offset_match.group(2)) if offset_match.group(2) else int(params_map.get("@limit", 100))

        # Load all documents from the table (optionally filtered by partition_key)
        db = await aiosqlite.connect(self._db_path)
        try:
            await db.execute("PRAGMA journal_mode=WAL")
            if self._partition_key is not None:
                cursor = await db.execute(
                    f'SELECT data FROM "{self._table}" WHERE partition_key = ?',
                    (self._partition_key,),
                )
            else:
                cursor = await db.execute(f'SELECT data FROM "{self._table}"')

            rows = await cursor.fetchall()
        finally:
            await db.close()

        docs = [json.loads(row[0]) for row in rows]

        # Apply WHERE conditions from the Cosmos query
        docs = self._apply_where(docs, query, params_map)

        # Apply ORDER BY
        docs = self._apply_order_by(docs, query)

        # Apply OFFSET / LIMIT or TOP
        if offset or limit:
            end = offset + limit if limit else len(docs)
            docs = docs[offset:end]
        elif top_n is not None:
            docs = docs[:top_n]

        # Return appropriate shape
        if is_count:
            return [len(docs)] if not (offset or limit or top_n) else [len(docs)]
        if select_field:
            return [{select_field: doc.get(select_field)} for doc in docs]

        return docs

    def _apply_where(
        self,
        docs: list[dict[str, Any]],
        query: str,
        params_map: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply WHERE clause filtering on in-memory documents."""
        import re

        # Extract WHERE clause
        where_match = re.search(
            r"WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+OFFSET|\s*$)",
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if not where_match:
            return docs

        where_clause = where_match.group(1).strip()
        conditions = self._parse_conditions(where_clause)

        filtered = []
        for doc in docs:
            if self._doc_matches(doc, conditions, params_map):
                filtered.append(doc)

        return filtered

    def _parse_conditions(self, where_clause: str) -> list[dict[str, Any]]:
        """Parse a WHERE clause into individual conditions."""
        import re

        conditions: list[dict[str, Any]] = []

        # Split on AND (simple approach — handles most Cosmos queries)
        parts = re.split(r"\s+AND\s+", where_clause, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not part or part == "1=1":
                continue

            # ARRAY_CONTAINS(c.field, @param)
            ac_match = re.match(
                r"ARRAY_CONTAINS\(c\.(\w+),\s*(@\w+)\)",
                part,
                re.IGNORECASE,
            )
            if ac_match:
                conditions.append({
                    "type": "array_contains",
                    "field": ac_match.group(1),
                    "param": ac_match.group(2),
                })
                continue

            # c.field.subfield = @param or c.field = @param or c.field = 'literal'
            eq_match = re.match(
                r"c\.([\w.]+)\s*(=|!=|>=|<=|>|<)\s*(@\w+|'[^']*')",
                part,
                re.IGNORECASE,
            )
            if eq_match:
                field_path = eq_match.group(1)
                operator = eq_match.group(2)
                value_ref = eq_match.group(3)
                conditions.append({
                    "type": "comparison",
                    "field": field_path,
                    "operator": operator,
                    "value_ref": value_ref,
                })
                continue

        return conditions

    def _doc_matches(
        self,
        doc: dict[str, Any],
        conditions: list[dict[str, Any]],
        params_map: dict[str, Any],
    ) -> bool:
        """Check if a doc satisfies all conditions."""
        for cond in conditions:
            ctype = cond["type"]

            if ctype == "array_contains":
                field_val = doc.get(cond["field"], [])
                param_val = params_map.get(cond["param"])
                if not isinstance(field_val, list) or param_val not in field_val:
                    return False

            elif ctype == "comparison":
                field_path = cond["field"]
                operator = cond["operator"]
                value_ref = cond["value_ref"]

                # Resolve the value
                if value_ref.startswith("@"):
                    compare_val = params_map.get(value_ref)
                else:
                    compare_val = value_ref.strip("'")

                # Resolve the field (supports dot-notation like trigger.type)
                doc_val = doc
                for part in field_path.split("."):
                    if isinstance(doc_val, dict):
                        doc_val = doc_val.get(part)
                    else:
                        doc_val = None
                        break

                if not self._compare(doc_val, operator, compare_val):
                    return False

        return True

    @staticmethod
    def _compare(doc_val: Any, operator: str, compare_val: Any) -> bool:
        """Evaluate a comparison operator."""
        if doc_val is None and compare_val is not None:
            return operator == "!="
        if operator == "=":
            return str(doc_val) == str(compare_val)
        if operator == "!=":
            return str(doc_val) != str(compare_val)
        if operator == ">=":
            return str(doc_val) >= str(compare_val)
        if operator == "<=":
            return str(doc_val) <= str(compare_val)
        if operator == ">":
            return str(doc_val) > str(compare_val)
        if operator == "<":
            return str(doc_val) < str(compare_val)
        return False

    def _apply_order_by(
        self,
        docs: list[dict[str, Any]],
        query: str,
    ) -> list[dict[str, Any]]:
        """Apply ORDER BY clause."""
        import re

        order_match = re.search(
            r"ORDER\s+BY\s+c\.([\w.]+)\s+(ASC|DESC)",
            query,
            re.IGNORECASE,
        )
        if not order_match:
            return docs

        field = order_match.group(1)
        direction = order_match.group(2).upper()

        def sort_key(doc: dict[str, Any]) -> tuple[int, float | str]:
            val = doc
            for part in field.split("."):
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = None
                    break
            if val is None:
                return (0, 0.0)
            # Coerce numeric strings so int/str mixes compare correctly
            if isinstance(val, (int, float)):
                return (1, float(val))
            try:
                return (1, float(val))
            except (TypeError, ValueError):
                return (2, str(val))

        return sorted(docs, key=sort_key, reverse=(direction == "DESC"))


# ---------------------------------------------------------------------------
# SQLiteDatabaseClient — mimics azure.cosmos.aio.DatabaseProxy
# ---------------------------------------------------------------------------


class SQLiteDatabaseClient:
    """Mimics azure.cosmos.aio.DatabaseProxy."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get_container_client(self, container_name: str) -> SQLiteContainerClient:
        return SQLiteContainerClient(self._db_path, container_name)


# ---------------------------------------------------------------------------
# SQLiteCosmosClient — mimics azure.cosmos.aio.CosmosClient
# ---------------------------------------------------------------------------


class SQLiteCosmosClient:
    """Mimics azure.cosmos.aio.CosmosClient.

    All databases map to the same SQLite file — the ``database_name`` parameter
    is accepted but ignored (a single-user desktop app only needs one DB).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._initialized = False

    async def ensure_initialized(self) -> None:
        """Create all tables if they don't exist."""
        if self._initialized:
            return

        db = await aiosqlite.connect(self._db_path)
        try:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA_DDL)
            await db.commit()
        finally:
            await db.close()

        self._initialized = True
        logger.info("SQLite database initialized at %s", self._db_path)

    def get_database_client(self, database_name: str) -> SQLiteDatabaseClient:
        return SQLiteDatabaseClient(self._db_path)

    async def close(self) -> None:
        """No-op — aiosqlite connections are opened/closed per operation."""
        pass
