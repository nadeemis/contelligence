"""Application startup and shutdown lifecycle hooks."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.settings import AppSettings, get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# Module-level references for admin router imports
_extraction_cache = None
_token_manager = None
_scheduler = None

# Module-level references for scheduling stack
_scheduling_engine = None
_run_tracker = None


async def _cleanup_on_startup_failure(app: FastAPI) -> None:
    """Best-effort cleanup of resources already attached to *app.state* when startup fails."""
    global _extraction_cache, _token_manager, _scheduler, _scheduling_engine, _run_tracker  # noqa: PLW0603

    # Scheduling engine
    if _scheduling_engine is not None:
        try:
            await _scheduling_engine.stop()
        except Exception:
            logger.debug("Error stopping scheduling engine during cleanup.", exc_info=True)
        _scheduling_engine = None

    if _run_tracker is not None:
        try:
            await _run_tracker.cancel_all_tracking()
        except Exception:
            logger.debug("Error during run tracker cleanup.", exc_info=True)
        _run_tracker = None

    # Scheduler leadership
    if _scheduler is not None:
        try:
            await _scheduler.release_leadership()
        except Exception:
            logger.debug("Error releasing scheduler leadership during cleanup.", exc_info=True)
        _scheduler = None

    # Token manager
    if _token_manager is not None:
        try:
            await _token_manager.stop()
        except Exception:
            logger.debug("Error stopping token manager during cleanup.", exc_info=True)
        _token_manager = None

    _extraction_cache = None

    # Close connectors
    for name in (
        "blob_connector",
        "search_connector",
        "cosmos_connector",
        "doc_intelligence_connector",
        "openai_connector",
    ):
        connector = getattr(app.state, name, None)
        if connector is not None and hasattr(connector, "close"):
            try:
                await connector.close()
                logger.debug("Closed %s during startup-failure cleanup.", name)
            except Exception:
                logger.debug("Error closing %s during cleanup.", name, exc_info=True)

    # Stop the Copilot SDK client (via factory)
    client_factory = getattr(app.state, "client_factory", None)
    if client_factory is not None:
        try:
            await client_factory.stop()
            logger.debug("Copilot client factory stopped during startup-failure cleanup.")
        except Exception:
            logger.debug("Error stopping Copilot client factory during cleanup.", exc_info=True)


async def on_startup(app: FastAPI) -> None:
    """Initialise connectors, Copilot client, tool registry, session factory, and agent service."""
    global _extraction_cache, _token_manager, _scheduler, _scheduling_engine, _run_tracker  # noqa: PLW0603
    settings = get_settings()

    # ------------------------------------------------------------------
    # Observability (FIRST — before anything else)
    # ------------------------------------------------------------------
    from app.observability import (
        configure_logging,
        initialize_observability,
        set_instance_context,
    )
    from app.utils.instance import get_instance_id

    initialize_observability()
    configure_logging(settings.LOG_LEVEL)
    set_instance_context(get_instance_id())

    logger.info("\n" + "-" * 100)
    logger.info("\n" + "-" * 100)
    logger.info("Starting Contelligence Agent...")

    try:
        await _do_startup(app, settings)
    except Exception:
        logger.exception("Application startup failed — cleaning up resources.")
        await _cleanup_on_startup_failure(app)
        raise


async def _do_startup(app: FastAPI, settings: AppSettings) -> None:  # noqa: ANN001
    """Inner startup logic; separated so the caller can catch and clean up."""
    global _extraction_cache, _token_manager, _scheduler, _scheduling_engine, _run_tracker  # noqa: PLW0603

    # ------------------------------------------------------------------
    # MCP telemetry configuration (early, before connectors)
    # ------------------------------------------------------------------
    from app.telemetry import configure_mcp_telemetry
    configure_mcp_telemetry()

    # ------------------------------------------------------------------
    # Connectors — use lazy initialisation (ensure_initialized on first use)
    # ------------------------------------------------------------------
    from app.connectors.blob_connector import BlobConnectorAdapter
    from app.connectors.cosmos_connector import CosmosConnectorAdapter
    from app.connectors.doc_intelligence_connector import DocIntelligenceConnectorAdapter
    from app.connectors.openai_connector import OpenAIConnectorAdapter
    from app.connectors.search_connector import SearchConnectorAdapter

    blob_connector = BlobConnectorAdapter(
        account_name=settings.AZURE_STORAGE_ACCOUNT_NAME,
        credential_type=settings.AZURE_STORAGE_CREDENTIAL_TYPE,
        account_key=settings.AZURE_STORAGE_KEY,
    )
    search_connector = SearchConnectorAdapter(
        account_name=settings.AZURE_SEARCH_ACCOUNT_NAME,
        credential_type=settings.AZURE_SEARCH_CREDENTIAL_TYPE,
        api_key=settings.AZURE_SEARCH_API_KEY,
        api_version=settings.AZURE_SEARCH_API_VERSION,
    )
    cosmos_connector = CosmosConnectorAdapter(
        endpoint=settings.AZURE_COSMOS_ENDPOINT,
        key=settings.AZURE_COSMOS_KEY,
        database_name=settings.AZURE_COSMOS_DATABASE,
    )
    doc_intelligence_connector = DocIntelligenceConnectorAdapter(
        endpoint=settings.AZURE_DOC_INTELLIGENCE_ENDPOINT,
        key=settings.AZURE_DOC_INTELLIGENCE_KEY,
    )
    openai_connector = OpenAIConnectorAdapter(
        endpoint=settings.AZURE_OPENAI_ENDPOINT,
        key=settings.AZURE_OPENAI_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
    )

    app.state.blob_connector = blob_connector
    app.state.search_connector = search_connector
    app.state.cosmos_connector = cosmos_connector
    app.state.doc_intelligence_connector = doc_intelligence_connector
    app.state.openai_connector = openai_connector

    # ------------------------------------------------------------------
    # Provision Cosmos DB containers (idempotent)
    # ------------------------------------------------------------------
    from app.provisioning.cosmos_provisioner import provision_cosmos_db
    
    await cosmos_connector.ensure_initialized()
    
    try:
        await provision_cosmos_db(
            cosmos_connector._client, settings.AZURE_COSMOS_DATABASE,
        )
    except Exception as e:
        logger.exception(f"Cosmos DB provisioning failed — {str(e)}. Ensure Cosmos DB is accessible and credentials are correct.")
        logger.exception(e)
        raise e

    # ------------------------------------------------------------------
    # Tool registry — register all 14 atomic tools
    # ------------------------------------------------------------------
    from app.core.tool_registry import ToolRegistry
    from app.tools import register_all_tools

    tool_registry = ToolRegistry()
    register_all_tools(tool_registry)
    app.state.tool_registry = tool_registry

    logger.info(
        f"Registered {len(tool_registry)} tools: {', '.join(tool_registry.get_tool_names())}"
    )

    # ------------------------------------------------------------------
    # Build tool context — passed to every tool handler at invocation
    # ------------------------------------------------------------------
    tool_context = {
        "blob": blob_connector,
        "search": search_connector,
        "cosmos": cosmos_connector,
        "doc_intelligence": doc_intelligence_connector,
        "openai": openai_connector,
        "settings": settings,
    }

    # ------------------------------------------------------------------
    # Resolve GitHub token: env first, Key Vault as fallback
    # ------------------------------------------------------------------
    from app.mcp.config import get_mcp_servers_config, resolve_github_token

    resolved_github_token: str | None = settings.GITHUB_COPILOT_TOKEN or None

    if not resolved_github_token and settings.KEY_VAULT_URL:
        resolved_github_token = await resolve_github_token(settings.KEY_VAULT_URL)
        if resolved_github_token:
            logger.info("GitHub token resolved from Key Vault (env not set).")
        else:
            logger.warning(
                "GitHub token not found in env or Key Vault — "
                "Copilot client and GitHub MCP server may be unavailable."
            )
    elif not resolved_github_token:
        logger.warning(
            "GITHUB_COPILOT_TOKEN not set and KEY_VAULT_URL not configured — "
            "GitHub token unavailable."
        )

    # ------------------------------------------------------------------
    # GitHub Copilot SDK client (via CopilotClientFactory)
    # ------------------------------------------------------------------
    from app.core.client_factory import CopilotClientFactory

    base_options: dict = {
        "log_level": "info",
        "auto_start": True,
        "auto_restart": True,
    }

    if settings.COPILOT_CLI_PATH:
        base_options["cli_path"] = settings.COPILOT_CLI_PATH
    if settings.COPILOT_CLI_URL:
        base_options["cli_url"] = settings.COPILOT_CLI_URL

    client_factory = CopilotClientFactory(
        base_options=base_options,
        github_token=resolved_github_token,
    )
    await client_factory.start()
    app.state.client_factory = client_factory

    logger.info("Copilot SDK client started via factory.")

    # ------------------------------------------------------------------
    # Skills Integration — SkillStore + SkillsManager
    # ------------------------------------------------------------------
    from app.skills.store import SkillStore
    from app.skills.manager import SkillsManager

    # Parse extra skill directories from comma-separated setting
    extra_skill_dirs: list[str] = [
        d.strip() for d in settings.EXTRA_SKILLS_DIRECTORIES.split(",") if d.strip()
    ]
    
    skill_store = SkillStore(
        cosmos_client=cosmos_connector._client,
        database_name=settings.AZURE_COSMOS_DATABASE,
    )
    app.state.skill_store = skill_store

    skills_manager = SkillsManager(
        skill_store=skill_store,
        blob_connector=blob_connector,
        extra_skill_directories=extra_skill_dirs,
    )
    app.state.skills_manager = skills_manager

    # Inject skills_manager into tool context so skill tools can use it
    tool_context["skills_manager"] = skills_manager

    # Ensure the skills blob container exists
    try:
        await blob_connector.ensure_container_exists("skills")
    except Exception as e:
        logger.warning(
            "Could not ensure 'skills' blob container exists: %s", e,
        )

    # Sync built-in skills from local filesystem to Cosmos + Blob
    try:
        count = await skills_manager.sync_built_in_skills()
        if count:
            logger.info("Synced %d built-in skill(s).", count)
    except Exception:
        logger.warning("Built-in skill sync failed — continuing.", exc_info=True)

    # ------------------------------------------------------------------
    # Build Azure OpenAI provider config (BYOK) if endpoint is configured
    # ------------------------------------------------------------------
    provider_config = None
    if settings.AZURE_OPENAI_ENDPOINT and "your-" not in settings.AZURE_OPENAI_ENDPOINT:
        provider_config = {
            "type": "azure",
            "base_url": settings.AZURE_OPENAI_ENDPOINT,
            "azure": {
                "api_version": settings.AZURE_OPENAI_API_VERSION,
            },
        }
        if settings.AZURE_OPENAI_KEY:
            provider_config["api_key"] = settings.AZURE_OPENAI_KEY

    # ------------------------------------------------------------------
    # MCP server configuration and GitHub token resolution
    # ------------------------------------------------------------------
    mcp_config = get_mcp_servers_config()

    if resolved_github_token and "github" in mcp_config:
        mcp_config["github"]["auth"]["token"] = resolved_github_token
        logger.info("GitHub MCP token set from resolved token.")
    elif not resolved_github_token:
        logger.warning(
            "GitHub PAT not resolved — GitHub MCP server will be unavailable."
        )

    app.state.mcp_config = mcp_config

    # ------------------------------------------------------------------
    # Session factory & agent service
    # ------------------------------------------------------------------
    from app.core.session_factory import SessionFactory
    from app.store.session_store import SessionStore

    session_factory = SessionFactory(
        client_factory=client_factory,
        tool_registry=tool_registry,
        tool_context=tool_context,
        default_model=settings.COPILOT_MODEL,
        provider_config=provider_config,
        mcp_servers=mcp_config,
        working_directory=settings.WORKING_DIRECTORY or None,
        skill_directories=skills_manager.get_skill_directories(),
    )

    # Preflight — fail fast if the SDK client can't complete a round-trip
    await session_factory.verify(full_probe=True)

    app.state.session_factory = session_factory
    
    # ------------------------------------------------------------------
    # Session store
    # ------------------------------------------------------------------
    session_store = SessionStore(
        cosmos_connector._client, settings.AZURE_COSMOS_DATABASE,
    )
    app.state.session_store = session_store

    # ------------------------------------------------------------------
    # Ensure agent-outputs blob container exists
    # ------------------------------------------------------------------
    try:
        await blob_connector.ensure_initialized()
        await blob_connector.ensure_container_exists(
            settings.AGENT_OUTPUTS_CONTAINER,
        )
    except Exception as e:
        logger.error(
            f"Could not ensure '{settings.AGENT_OUTPUTS_CONTAINER}' blob container exists. "
            "Large-result offloading may fail."
        )
        logger.exception(e)
        raise e

    # ------------------------------------------------------------------
    # Phase 3 — Agent Delegator
    # ------------------------------------------------------------------
    from app.services.delegator import AgentDelegator

    # Custom Agent Management — AgentStore + DynamicAgentRegistry
    from app.agents.dynamic_registry import DynamicAgentRegistry
    from app.store.agent_store import AgentStore

    agent_store = AgentStore(
        cosmos_client=cosmos_connector._client,
        database_name=settings.AZURE_COSMOS_DATABASE,
    )
    app.state.agent_store = agent_store

    dynamic_registry = DynamicAgentRegistry(
        agent_store=agent_store, 
        cache_ttl_seconds=settings.DYNAMIC_REGISTRY_CACHE_TTL_SECONDS
        )
    app.state.dynamic_registry = dynamic_registry

    delegator = AgentDelegator(
        session_factory=session_factory,
        session_store=session_store,
        dynamic_registry=dynamic_registry,
    )
    app.state.delegator = delegator

    # Inject delegator into tool_context so delegate_task tool can use it
    tool_context["delegator"] = delegator
    
    # ------------------------------------------------------------------
    # Approval Manager
    # ------------------------------------------------------------------
    from app.services.approval_manager import ApprovalManager

    approval_manager = ApprovalManager(
        timeout_seconds=settings.APPROVAL_TIMEOUT_SECONDS,
    )
    app.state.approval_manager = approval_manager

    # ------------------------------------------------------------------
    # PersistentAgentService (main agent orchestration service, used by API routes) — depends on session factory, store, delegator, approval manager, and dynamic registry
    # ------------------------------------------------------------------
    from app.prompts.system_prompt import CONTELLIGENCE_AGENT_SYSTEM_PROMPT
    from app.services.persistent_agent_service import PersistentAgentService
    
    agent_service = PersistentAgentService(
        session_factory=session_factory,
        session_store=session_store,
        system_prompt=CONTELLIGENCE_AGENT_SYSTEM_PROMPT,
        blob_connector=blob_connector,
        outputs_container=settings.AGENT_OUTPUTS_CONTAINER,
        large_result_threshold=settings.LARGE_RESULT_THRESHOLD_KB * 1024,
        approval_manager=approval_manager,
        dynamic_registry=dynamic_registry,
        skills_manager=skills_manager,
    )
    app.state.agent_service = agent_service

    # ------------------------------------------------------------------
    # Rate Limiter
    # ------------------------------------------------------------------
    from app.rate_limiting import configure_default_rate_limits

    configure_default_rate_limits(settings)
    logger.info("Rate limits configured.")

    # ------------------------------------------------------------------
    # Extraction Cache
    # ------------------------------------------------------------------
    if settings.CACHE_ENABLED:
        try:
            from app.caching import ExtractionCache

            await cosmos_connector.ensure_initialized()
            db = cosmos_connector._client.get_database_client(
                settings.AZURE_COSMOS_DATABASE,
            )
            cache_container = db.get_container_client("extraction-cache")
            _extraction_cache = ExtractionCache(
                container=cache_container,
                ttl_days=settings.CACHE_TTL_DAYS,
            )
            app.state.extraction_cache = _extraction_cache
            logger.info("Extraction cache enabled (TTL=%dd).", settings.CACHE_TTL_DAYS)
        except Exception as e:
            logger.error(
                "Extraction cache init failed — caching disabled."
            )
            logger.exception(e)

    # ------------------------------------------------------------------
    # Key Vault Token Manager
    # ------------------------------------------------------------------
    if settings.KEY_VAULT_URL:
        try:
            from azure.identity.aio import DefaultAzureCredential
            from azure.keyvault.secrets.aio import SecretClient

            from app.auth.token_manager import TokenManager

            kv_credential = DefaultAzureCredential()
            kv_client = SecretClient(
                vault_url=settings.KEY_VAULT_URL,
                credential=kv_credential,
            )
            _token_manager = TokenManager(secret_client=kv_client)
            await _token_manager.start()
            app.state.token_manager = _token_manager
            logger.info("Token manager started.")
        except Exception as e:
            logger.error("Token manager init failed.")
            logger.exception(e)

    # ------------------------------------------------------------------
    # Scheduler Leader Election + Scheduling Engine
    # ------------------------------------------------------------------
    try:
        from app.retention import RetentionCleanup, RetentionPolicy
        from app.scheduling import SchedulerLeaderElection
        from app.services.schedule_run_tracker import ScheduleRunTracker
        from app.services.schedule_service import ScheduleService
        from app.services.schedule_store import ScheduleStore
        from app.services.scheduling_engine import SchedulingEngine

        await cosmos_connector.ensure_initialized()
        from app.utils.instance import get_instance_id as _get_instance_id

        retention_policy = RetentionPolicy(
            session_retention_days=settings.SESSION_RETENTION_DAYS,
            blob_archive_days=settings.BLOB_ARCHIVE_DAYS,
            blob_delete_days=settings.BLOB_DELETE_DAYS,
        )
        retention_cleanup = RetentionCleanup(
            session_store=session_store,
            blob_connector=blob_connector,
            retention_policy=retention_policy,
        )

        # Schedule Store
        schedule_store = ScheduleStore(
            cosmos_connector._client, settings.AZURE_COSMOS_DATABASE,
        )
        app.state.schedule_store = schedule_store

        # Run Tracker (fire_callback for SchedulingEngine)
        _run_tracker = ScheduleRunTracker(
            agent_service=agent_service,
            schedule_store=schedule_store,
            session_store=session_store,
        )
        app.state.run_tracker = _run_tracker

        # Scheduling Engine
        _scheduling_engine = SchedulingEngine(
            schedule_store=schedule_store,
            fire_callback=_run_tracker.fire_and_track,
            misfire_grace_time=settings.SCHEDULER_MISFIRE_GRACE_TIME,
        )
        app.state.scheduling_engine = _scheduling_engine

        # Schedule Service
        schedule_service = ScheduleService(
            store=schedule_store,
            engine=_scheduling_engine,
            agent_base_url=settings.AGENT_BASE_URL,
        )
        app.state.schedule_service = schedule_service

        # Leader election with scheduling engine callbacks
        _scheduler = SchedulerLeaderElection(
            cosmos_client=cosmos_connector._client,
            instance_id=_get_instance_id(),
            database_name=settings.AZURE_COSMOS_DATABASE,
        )

        async def on_become_leader() -> None:
            logger.info("This instance is now the scheduler leader.")
            await _scheduling_engine.start()

        async def on_lose_leadership() -> None:
            logger.warning("This instance lost scheduler leadership.")
            await _scheduling_engine.stop()

        # Run the leader loop as a background task
        asyncio.create_task(
            _scheduler.run_leader_loop(on_become_leader, on_lose_leadership),
        )
        app.state.scheduler = _scheduler
        app.state.retention_cleanup = retention_cleanup
        logger.info("Scheduler leader election + scheduling engine started.")
    except Exception as e:
        logger.error(
            "Scheduler leader election / scheduling engine init failed — "
            "scheduled jobs and retention cleanup disabled."
        )
        logger.exception(e)

    logger.info("Contelligence Agent started successfully.")
    logger.info(f"Startup complete. API available at http://{settings.API_HOST}:{settings.API_PORT}/{settings.API_VERSION}")
    logger.info(f"Registered tools: {', '.join(tool_registry.get_tool_names())}")
    logger.info(f"Registered MCP servers: {', '.join(mcp_config.keys()) if mcp_config else 'None'}")
    logger.info(f"Extra skill directories: {', '.join(extra_skill_dirs) if extra_skill_dirs else 'None'}")
    print("\n" + "-" * 75)
    print("\n" + "-" * 75)
    banner = (
        "\n"
        "   ____            _       _ _ _                            \n"
        "  / ___|___  _ __ | |_ ___| | (_) __ _  ___ _ __   ___ ___ \n"
        " | |   / _ \\| '_ \\| __/ _ \\ | | |/ _` |/ _ \\ '_ \\ / __/ _ \\\n"
        " | |__| (_) | | | | ||  __/ | | | (_| |  __/ | | | (_|  __/\n"
        "  \\____\\___/|_| |_|\\__\\___|_|_|_|\\__, |\\___|_| |_|\\___\\___|\n"
        "                                  |___/                     \n"
    )
    print(banner)
    print("\n" + "-" * 75)
    print("\n" + "-" * 75)

async def on_shutdown(app: FastAPI) -> None:
    """Gracefully shut down all connectors, active sessions, and the Copilot client."""
    global _extraction_cache, _token_manager, _scheduler, _scheduling_engine, _run_tracker  # noqa: PLW0603
    logger.info("Shutting down Contelligence Agent...")

    # Stop scheduling engine and run tracker
    if _scheduling_engine is not None:
        try:
            await _scheduling_engine.stop()
            logger.info("Scheduling engine stopped.")
        except Exception as e:
            logger.error("Error stopping scheduling engine.")
            logger.exception(e)
        _scheduling_engine = None

    if _run_tracker is not None:
        try:
            await _run_tracker.cancel_all_tracking()
            logger.info("Run tracker cleanup complete.")
        except Exception as e:
            logger.error("Error during run tracker cleanup.")
            logger.exception(e)
        _run_tracker = None

    # Release scheduler leadership
    if _scheduler is not None:
        try:
            await _scheduler.release_leadership()
            logger.info("Scheduler leadership released.")
        except Exception as e:
            logger.error("Error releasing scheduler leadership.")
            logger.exception(e)
        _scheduler = None

    # Stop token manager
    if _token_manager is not None:
        try:
            await _token_manager.stop()
            logger.info("Token manager stopped.")
        except Exception as e:
            logger.error("Error stopping token manager.")
            logger.exception(e)
        _token_manager = None

    _extraction_cache = None

    # Shut down connectors
    for name in (
        "blob_connector",
        "search_connector",
        "cosmos_connector",
        "doc_intelligence_connector",
        "openai_connector",
    ):
        connector = getattr(app.state, name, None)
        if connector is not None and hasattr(connector, "close"):
            try:
                await connector.close()
                logger.info("Closed %s.", name)
            except Exception as e:
                logger.error("Error closing %s.", name)
                logger.exception(e)

    # Stop the Copilot SDK client (via factory)
    client_factory = getattr(app.state, "client_factory", None)
    if client_factory is not None:
        try:
            await client_factory.stop()
            logger.info("Copilot client factory stopped.")
        except Exception as e:
            logger.error("Error stopping Copilot client factory.")
            logger.exception(e)

    logger.info("Contelligence Agent shut down.")
