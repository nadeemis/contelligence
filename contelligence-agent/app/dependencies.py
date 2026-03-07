"""FastAPI dependency injection functions."""

from __future__ import annotations

from fastapi import Request

from app.connectors.blob_connector import BlobConnectorAdapter
from app.connectors.cosmos_connector import CosmosConnectorAdapter
from app.connectors.doc_intelligence_connector import DocIntelligenceConnectorAdapter
from app.connectors.openai_connector import OpenAIConnectorAdapter
from app.connectors.search_connector import SearchConnectorAdapter
from app.services.persistent_agent_service import PersistentAgentService
from app.settings import AppSettings
from app.settings import get_settings as _get_settings
from app.store.session_store import SessionStore


def get_settings() -> AppSettings:
    return _get_settings()


def get_agent_service(request: Request) -> PersistentAgentService:
    return request.app.state.agent_service


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_blob_connector(request: Request) -> BlobConnectorAdapter:
    return request.app.state.blob_connector


def get_search_connector(request: Request) -> SearchConnectorAdapter:
    return request.app.state.search_connector


def get_cosmos_connector(request: Request) -> CosmosConnectorAdapter:
    return request.app.state.cosmos_connector


def get_doc_intelligence_connector(request: Request) -> DocIntelligenceConnectorAdapter:
    return request.app.state.doc_intelligence_connector


def get_openai_connector(request: Request) -> OpenAIConnectorAdapter:
    return request.app.state.openai_connector


# Delegation and approval

def get_delegator(request: Request):
    """Return the ``AgentDelegator`` singleton."""
    from app.services.delegator import AgentDelegator
    return request.app.state.delegator


def get_approval_manager(request: Request):
    """Return the ``ApprovalManager`` singleton."""
    from app.services.approval_manager import ApprovalManager
    return request.app.state.approval_manager


# Additional dependencies

def get_extraction_cache(request: Request):
    """Return the ``ExtractionCache`` singleton (or ``None`` if disabled)."""
    return getattr(request.app.state, "extraction_cache", None)


def get_token_manager(request: Request):
    """Return the ``TokenManager`` singleton (or ``None`` if not configured)."""
    return getattr(request.app.state, "token_manager", None)


def get_scheduler(request: Request):
    """Return the ``SchedulerLeaderElection`` singleton (or ``None``)."""
    return getattr(request.app.state, "scheduler", None)


# Custom Agent Management — agent store, dynamic registry, tool registry

def get_agent_store(request: Request):
    """Provide the ``AgentStore`` singleton."""
    from app.store.agent_store import AgentStore
    return request.app.state.agent_store


def get_dynamic_registry(request: Request):
    """Provide the ``DynamicAgentRegistry`` singleton."""
    from app.agents.dynamic_registry import DynamicAgentRegistry
    return request.app.state.dynamic_registry


def get_tool_registry(request: Request):
    """Provide the ``ToolRegistry`` singleton."""
    from app.core.tool_registry import ToolRegistry
    return request.app.state.tool_registry


def get_client_factory(request: Request):
    """Provide the ``CopilotClientFactory`` singleton."""
    from app.core.client_factory import CopilotClientFactory
    return request.app.state.client_factory


# Scheduling Engine dependencies

def get_schedule_store(request: Request):
    """Return the ``ScheduleStore`` singleton (or ``None``)."""
    return getattr(request.app.state, "schedule_store", None)


def get_scheduling_engine(request: Request):
    """Return the ``SchedulingEngine`` singleton (or ``None``)."""
    return getattr(request.app.state, "scheduling_engine", None)


def get_schedule_service(request: Request):
    """Return the ``ScheduleService`` singleton (or ``None``)."""
    return getattr(request.app.state, "schedule_service", None)


def get_run_tracker(request: Request):
    """Return the ``ScheduleRunTracker`` singleton (or ``None``)."""
    return getattr(request.app.state, "run_tracker", None)


# Skills Integration dependencies

def get_skills_manager(request: Request):
    """Return the ``SkillsManager`` singleton (or ``None`` if disabled)."""
    return getattr(request.app.state, "skills_manager", None)
