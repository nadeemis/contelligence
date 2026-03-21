"""Agent Management Router — CRUD for custom agent definitions.

Provides REST endpoints for creating, reading, updating, deleting,
cloning, and testing user-defined agent personas.

Phase: Custom Agent Management
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.agents.dynamic_registry import DynamicAgentRegistry
from app.core.tool_registry import ToolRegistry
from app.dependencies import get_agent_store, get_dynamic_registry, get_tool_registry
from app.mcp.file_config import APP_CONFIG_PATH, SHARED_CONFIG_PATH
from app.models.custom_agent_models import (
    AgentDefinitionRecord,
    AgentSource,
    AgentStatus,
)
from app.store.agent_store import AgentAlreadyExistsError, AgentNotFoundError, AgentStore

logger = logging.getLogger(f"contelligence-agent.{__name__}")

router = APIRouter(prefix="/agents", tags=["Agents"])


# ── Request / Response Models ──────────────────────────────────


class CreateAgentRequest(BaseModel):
    """Payload for creating a new custom agent."""

    id: str = Field(
        description="Unique slug identifier (lowercase, hyphens, 3-40 chars)",
        pattern=r"^[a-z][a-z0-9-]{2,39}$",
    )
    display_name: str = Field(description="Human-readable name", max_length=100)
    description: str = Field(description="One-line summary", max_length=300)
    prompt: str = Field(description="Full system prompt", max_length=10000)
    tools: list[str] = Field(description="Atomic tool names to allow")
    model: str = Field(default="gpt-4.1")
    max_tool_calls: int = Field(default=50, ge=1, le=500)
    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    icon: str = Field(default="bot", max_length=50)
    tags: list[str] = Field(default_factory=list)
    status: AgentStatus = Field(default=AgentStatus.DRAFT)
    bound_skills: list[str] = Field(
        default_factory=list,
        description="Skill names whose instructions are auto-loaded at session start",
    )


class UpdateAgentRequest(BaseModel):
    """Payload for updating an existing agent (all fields optional)."""

    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    prompt: str | None = Field(default=None, max_length=10000)
    tools: list[str] | None = None
    model: str | None = None
    max_tool_calls: int | None = Field(default=None, ge=1, le=500)
    timeout_seconds: int | None = Field(default=None, ge=30, le=3600)
    icon: str | None = Field(default=None, max_length=50)
    tags: list[str] | None = None
    status: AgentStatus | None = None
    bound_skills: list[str] | None = None


class AgentSummary(BaseModel):
    """Summary of an agent for list endpoints."""

    id: str
    display_name: str
    description: str
    source: str
    status: str
    tools: list[str] | None
    model: str
    max_tool_calls: int
    timeout_seconds: int
    tags: list[str]
    icon: str
    usage_count: int
    editable: bool
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class TestAgentRequest(BaseModel):
    """Payload for dry-run testing an agent definition."""

    instruction: str = Field(
        description="Test instruction to send to the agent",
        max_length=2000,
    )
    max_turns: int = Field(
        default=3,
        description="Max reasoning turns (keeps test fast)",
        ge=1,
        le=10,
    )


class TestAgentResponse(BaseModel):
    """Result of a dry-run agent test."""

    agent_id: str
    instruction: str
    response: str
    tool_calls: list[dict[str, Any]]
    turns: int
    duration_ms: int
    warnings: list[str]


class ToolInfo(BaseModel):
    """Metadata about an available tool."""

    name: str
    description: str
    category: str

# ── Tool category mapping ──────────────────────────────────────

_TOOL_CATEGORIES: dict[str, str] = {
    "extract_pdf": "extraction",
    "extract_docx": "extraction",
    "extract_xlsx": "extraction",
    "extract_pptx": "extraction",
    "call_doc_intelligence": "extraction",
    "scrape_webpage": "extraction",
    "transcribe_audio": "extraction",
    "read_blob": "storage",
    "write_blob": "storage",
    "upload_to_search": "storage",
    "upsert_cosmos": "storage",
    "query_search_index": "query",
    "query_cosmos": "query",
    "generate_embeddings": "ai",
}


# ── Endpoints ──────────────────────────────────────────────────


@router.get("", response_model=list[AgentSummary])
async def list_agents(
    status: AgentStatus | None = Query(None, description="Filter by status"),
    source: str | None = Query(None, description="Filter: 'built-in' or 'user-created'"),
    tag: str | None = Query(None, description="Filter by tag"),
    registry: DynamicAgentRegistry = Depends(get_dynamic_registry),
) -> list[AgentSummary]:
    """List all agents (built-in + user-created) with optional filters."""
    agents = await registry.list_available_agents()

    if status:
        agents = [a for a in agents if a["status"] == status.value]
    if source:
        agents = [a for a in agents if a["source"] == source]
    if tag:
        agents = [a for a in agents if tag in a.get("tags", [])]

    return [AgentSummary(**a) for a in agents]


@router.get("/tools", response_model=list[ToolInfo])
async def list_available_tools(
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> list[ToolInfo]:
    """List all registered atomic tools that can be assigned to agents.

    This endpoint powers the tool-selection UI in the agent editor.
    """
    tools = tool_registry.get_all_tools()
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            category=_TOOL_CATEGORIES.get(t.name, "other"),
        )
        for t in tools
    ]


@router.post("", response_model=AgentDefinitionRecord, status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    store: AgentStore = Depends(get_agent_store),
    registry: DynamicAgentRegistry = Depends(get_dynamic_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> AgentDefinitionRecord:
    """Create a new custom agent definition."""
    from app.agents.custom_agents import CUSTOM_AGENTS

    # Validate that the ID doesn't collide with a built-in agent
    if body.id in CUSTOM_AGENTS:
        raise HTTPException(
            status_code=409,
            detail=f"'{body.id}' is a built-in agent and cannot be overridden",
        )

    # Validate tools exist
    available = set(tool_registry.get_tool_names())
    unknown_tools = set(body.tools) - available
    if unknown_tools:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown tools: {sorted(unknown_tools)}. Available: {sorted(available)}",
        )

    now = datetime.now(timezone.utc)
    record = AgentDefinitionRecord(
        id=body.id,
        display_name=body.display_name,
        description=body.description,
        prompt=body.prompt,
        tools=body.tools,
        model=body.model,
        max_tool_calls=body.max_tool_calls,
        timeout_seconds=body.timeout_seconds,
        icon=body.icon,
        tags=body.tags,
        status=body.status,
        bound_skills=body.bound_skills,
        source=AgentSource.USER_CREATED,
        created_at=now,
        updated_at=now,
    )

    try:
        result = await store.create_agent(record)
    except AgentAlreadyExistsError:
        raise HTTPException(
            status_code=409, detail=f"Agent '{body.id}' already exists",
        )

    registry.invalidate_cache()
    return result


@router.get("/{agent_id}", response_model=AgentDefinitionRecord)
async def get_agent(
    agent_id: str,
    store: AgentStore = Depends(get_agent_store),
) -> AgentDefinitionRecord:
    """Get full details of a single agent."""
    from app.agents.custom_agents import CUSTOM_AGENTS

    # Check built-in first
    if agent_id in CUSTOM_AGENTS:
        defn = CUSTOM_AGENTS[agent_id]
        return AgentDefinitionRecord(
            id=agent_id,
            display_name=defn.display_name,
            description=defn.description,
            prompt=defn.prompt,
            tools=defn.tools,
            model=defn.model,
            max_tool_calls=defn.max_tool_calls,
            timeout_seconds=defn.timeout_seconds,
            source=AgentSource.BUILT_IN,
            status=AgentStatus.ACTIVE,
        )

    try:
        return await store.get_agent(agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@router.put("/{agent_id}", response_model=AgentDefinitionRecord)
async def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    store: AgentStore = Depends(get_agent_store),
    registry: DynamicAgentRegistry = Depends(get_dynamic_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> AgentDefinitionRecord:
    """Update an existing user-created agent."""
    from app.agents.custom_agents import CUSTOM_AGENTS

    if agent_id in CUSTOM_AGENTS:
        raise HTTPException(
            status_code=403,
            detail="Built-in agents cannot be modified. Clone it to create an editable copy.",
        )

    try:
        record = await store.get_agent(agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # Apply partial update
    update_data = body.model_dump(exclude_unset=True)

    # Validate tools if being updated
    if "tools" in update_data:
        available = set(tool_registry.get_tool_names())
        unknown = set(update_data["tools"]) - available
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown tools: {sorted(unknown)}",
            )

    for field, value in update_data.items():
        setattr(record, field, value)

    result = await store.update_agent(record)
    registry.invalidate_cache()
    return result


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    store: AgentStore = Depends(get_agent_store),
    registry: DynamicAgentRegistry = Depends(get_dynamic_registry),
) -> None:
    """Permanently delete a user-created agent."""
    from app.agents.custom_agents import CUSTOM_AGENTS

    if agent_id in CUSTOM_AGENTS:
        raise HTTPException(status_code=403, detail="Built-in agents cannot be deleted")

    try:
        await store.delete_agent(agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    registry.invalidate_cache()


@router.post("/{agent_id}/clone", response_model=AgentDefinitionRecord, status_code=201)
async def clone_agent(
    agent_id: str,
    new_id: str = Query(
        ...,
        pattern=r"^[a-z][a-z0-9-]{2,39}$",
        description="ID for the clone",
    ),
    store: AgentStore = Depends(get_agent_store),
    registry: DynamicAgentRegistry = Depends(get_dynamic_registry),
) -> AgentDefinitionRecord:
    """Clone an existing agent (built-in or user-created) into a new editable copy.

    This is the primary mechanism for customizing built-in agents: clone first,
    then edit the clone.
    """
    from app.agents.custom_agents import CUSTOM_AGENTS

    # Resolve source agent
    if agent_id in CUSTOM_AGENTS:
        defn = CUSTOM_AGENTS[agent_id]
        source_record = AgentDefinitionRecord(
            id=agent_id,
            display_name=defn.display_name,
            description=defn.description,
            prompt=defn.prompt,
            tools=defn.tools,
            model=defn.model,
            max_tool_calls=defn.max_tool_calls,
            timeout_seconds=defn.timeout_seconds,
        )
    else:
        try:
            source_record = await store.get_agent(agent_id)
        except AgentNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Agent '{agent_id}' not found",
            )

    now = datetime.now(timezone.utc)
    clone = AgentDefinitionRecord(
        id=new_id,
        display_name=f"{source_record.display_name} (Copy)",
        description=source_record.description,
        prompt=source_record.prompt,
        tools=source_record.tools,
        model=source_record.model,
        max_tool_calls=source_record.max_tool_calls,
        timeout_seconds=source_record.timeout_seconds,
        icon=getattr(source_record, "icon", "bot"),
        tags=list(getattr(source_record, "tags", [])),
        bound_skills=list(getattr(source_record, "bound_skills", [])),
        source=AgentSource.USER_CREATED,
        status=AgentStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )

    try:
        result = await store.create_agent(clone)
    except AgentAlreadyExistsError:
        raise HTTPException(
            status_code=409, detail=f"Agent '{new_id}' already exists",
        )

    registry.invalidate_cache()
    return result


@router.post("/{agent_id}/test", response_model=TestAgentResponse)
async def test_agent(
    agent_id: str,
    body: TestAgentRequest,
    registry: DynamicAgentRegistry = Depends(get_dynamic_registry),
) -> TestAgentResponse:
    """Dry-run test an agent with a sample instruction.

    Runs the agent in a sandboxed sub-session with reduced limits and
    returns the reasoning trace without persisting outputs.
    """
    agent = await registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # Implementation delegates to a sandboxed version of AgentDelegator
    # with persist_outputs=False, max_tool_calls=body.max_turns, timeout=30s
    # Full implementation deferred to a later iteration.
    raise HTTPException(status_code=501, detail="Test endpoint not yet implemented")
