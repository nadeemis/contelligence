"""Application startup and shutdown lifecycle hooks."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
from typing import TYPE_CHECKING

from pathlib import Path

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
        "app_storage_manager",
        "app_storage_connector",
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
    # Connectors and Storage — branch on STORAGE_MODE (azure vs. local)
    # Provision database containers (idempotent) — Cosmos DB or SQLite
    # ------------------------------------------------------------------
    is_local = settings.STORAGE_MODE == "local"

    if is_local:
        from pathlib import Path

        from app.connectors.local_blob_connector import LocalBlobConnectorAdapter
        from app.connectors.sqlite_connector import SQLiteCosmosClient
        from app.store.storage_manager import SQLiteStorageManager

        # Resolve data directory
        data_dir = settings.app_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        blobs_dir = str(data_dir / "blobs")
        db_path = str(data_dir / "contelligence.db")

        logger.info(f"Local mode — data dir: {data_dir}, db: {db_path}")

        # SQLite-backed Cosmos shim
        sqlite_client = SQLiteCosmosClient(db_path)
        await sqlite_client.ensure_initialized()

        logger.info("SQLite tables ready (local mode).")
        app_storage_manager = SQLiteStorageManager(
            sqlite_client=sqlite_client,
            database_name=settings.APP_STORAGE_DATABASE,
        )
        
        # Store the SQLite client where stores/provisioner normally expect the Cosmos client
        app.state.app_storage_client = sqlite_client

        app_storage_connector = LocalBlobConnectorAdapter(base_dir=blobs_dir)
        
    else:
        # Azure deployment — use connectors for Cosmos DB and Blob Storage
        
        from app.connectors.blob_connector import BlobConnectorAdapter
        from app.connectors.cosmos_connector import CosmosConnectorAdapter
        from app.store.storage_manager import CosmosStorageManager
        
        cosmos_connector = CosmosConnectorAdapter(
            endpoint=settings.APP_STORAGE_COSMOS_ENDPOINT,
            key=settings.APP_STORAGE_COSMOS_KEY,
            database_name=settings.APP_STORAGE_DATABASE,
        )
        
        from app.provisioning.cosmos_provisioner import provision_cosmos_db

        await cosmos_connector.ensure_initialized()
        app.state.app_storage_client = cosmos_connector._client

        try:
            await provision_cosmos_db(
                cosmos_connector._client, settings.APP_STORAGE_DATABASE,
            )
        except Exception as e:
            logger.exception(f"Cosmos DB provisioning failed — {str(e)}. Ensure Cosmos DB is accessible and credentials are correct.")
            logger.exception(e)
            raise e

        app_storage_manager = CosmosStorageManager(
            cosmos_connector=cosmos_connector,
            database_name=settings.APP_STORAGE_DATABASE,
        )

        app.state.app_storage_client = None  # will be set after initialization
        
        app_storage_connector = BlobConnectorAdapter(
            account_name=settings.APP_AZURE_STORAGE_ACCOUNT_NAME,
            credential_type=settings.APP_AZURE_STORAGE_CREDENTIAL_TYPE,
            account_key=settings.APP_AZURE_STORAGE_KEY,
        )
        
    app.state.app_storage_manager = app_storage_manager
    app.state.app_storage_connector = app_storage_connector

    # ------------------------------------------------------------------
    # Prompt Store — customisable system & agent prompts
    # ------------------------------------------------------------------
    from app.prompts.prompt_store import PromptStore

    prompt_store = PromptStore(storage_manager=app_storage_manager)
    app.state.prompt_store = prompt_store
    logger.info("Prompt store initialised.")

    # ------------------------------------------------------------------
    # Tool registry — register all atomic tools
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
        "app_storage_connector": app_storage_connector,
        "app_storage_manager": app_storage_manager,
        "app_storage_client": app.state.app_storage_client,  # Cosmos client or SQLite client, depending on mode
        "settings": settings,
    }

    # ------------------------------------------------------------------
    # Resolve GitHub token: env first, Key Vault as fallback
    # ------------------------------------------------------------------
    from app.utils.github_token_helper import resolve_github_token

    resolved_github_token: str | None = settings.GITHUB_COPILOT_TOKEN or None

    if not resolved_github_token and settings.KEY_VAULT_ENDPOINT:
        resolved_github_token = await resolve_github_token(settings.KEY_VAULT_ENDPOINT)
        if resolved_github_token:
            logger.info("GitHub token resolved from Key Vault (env not set).")
        else:
            logger.warning(
                "GitHub token not found in env or Key Vault — "
                "Copilot client and GitHub MCP server may be unavailable."
            )
    elif not resolved_github_token:
        logger.warning(
            "GITHUB_COPILOT_TOKEN not set and KEY_VAULT_ENDPOINT not configured — "
            "GitHub token unavailable."
        )

    # ------------------------------------------------------------------
    # MCP server configuration
    # ------------------------------------------------------------------
    from app.mcp.config import get_mcp_servers_config
    from app.mcp.file_config import ensure_default_config

    ensure_default_config()  # scaffold ~/.contelligence/mcp-config.json on first run
    mcp_config = get_mcp_servers_config()

    # if resolved_github_token and "github" in mcp_config:
    #     mcp_config["github"]["auth"]["token"] = resolved_github_token
    #     logger.info("GitHub MCP token set from resolved token.")
    # elif not resolved_github_token:
    #     logger.warning(
    #         "GitHub PAT not resolved — GitHub MCP server will be unavailable."
    #     )

    app.state.mcp_config = mcp_config


    # ------------------------------------------------------------------
    # GitHub Copilot SDK client (via CopilotClientFactory)
    # ------------------------------------------------------------------
    from app.core.client_factory import CopilotClientFactory

    base_options: dict = {
        "log_level": settings.LOG_LEVEL.lower() if settings.LOG_LEVEL else "info",
        "auto_start": True,
        "cli_cwd": os.path.expanduser(settings.CLI_WORKING_DIRECTORY) if settings.CLI_WORKING_DIRECTORY else None,
        "cli_args": settings.COPILOT_CLI_ARGS or [],
    }

    cli_path = settings.COPILOT_CLI_PATH
    # On Windows, npm global installs create a shell-script wrapper without
    # an extension that cannot be launched by subprocess directly.  The real
    # Windows launcher is the .cmd sibling.
    if cli_path and platform.system() == "Windows":
        from pathlib import Path as _P
        _cli = _P(cli_path)
        if not _cli.suffix and _cli.with_suffix(".cmd").exists():
            cli_path = str(_cli.with_suffix(".cmd"))

    if cli_path:
        base_options["cli_path"] = cli_path
    if settings.COPILOT_CLI_URL:
        base_options["cli_path"] = ""  # Clear cli_path if URL is set, to avoid conflicts
        base_options["cli_url"] = settings.COPILOT_CLI_URL

    logger.debug(f"Starting Copilot client using cli_path: {settings.COPILOT_CLI_PATH}" \
            if settings.COPILOT_CLI_PATH else f"Starting Copilot client using cli_url: {settings.COPILOT_CLI_URL}" \
            if settings.COPILOT_CLI_URL else "Starting Copilot client with default CLI path resolution.")
    
    client_factory = CopilotClientFactory(
        base_options=base_options,
        github_token=resolved_github_token,
    )
    try:
        await client_factory.start()
        logger.info("Copilot SDK client started via factory.")
    except RuntimeError as exc:
        logger.warning(
            "Copilot CLI startup failed — AI features will be unavailable: %s",
            exc,
        )
    app.state.client_factory = client_factory

    # ------------------------------------------------------------------
    # Skills Integration — SkillStore + SkillsManager
    # ------------------------------------------------------------------
    from app.skills.store import SkillStore
    from app.skills.manager import SkillsManager

    skill_store = SkillStore(
        storage_manager=app_storage_manager,
    )
    app.state.skill_store = skill_store

    skills_manager = SkillsManager(
        skill_store=skill_store,
        settings=settings,
    )
    app.state.skills_manager = skills_manager

    # Inject skills_manager into tool context so skill tools can use it
    tool_context["skills_manager"] = skills_manager

    logger.info(f"Synchronizing skills... to shared directory {settings.AGENT_SHARED_SKILLS_DIRECTORY or '(not configured)'}")

    # Sync built-in skills from local filesystem to Cosmos metadata + shared dir
    try:
        logger.debug("Syncing built-in skills...")
        count = await skills_manager.sync_built_in_skills()
        if count:
            logger.info("Synced %d built-in skill(s).", count)
    except Exception:
        logger.warning("Built-in skill sync failed — continuing.", exc_info=True)

    # Discover any manually-added skills in the shared directory
    try:
        discovered = await skills_manager.discover_filesystem_skills()
        if discovered:
            logger.info("Discovered %d new skill(s) from filesystem.", discovered)
    except Exception:
        logger.warning("Filesystem skill discovery failed — continuing.", exc_info=True)

    # ------------------------------------------------------------------
    # Build Azure OpenAI provider config (BYOK) if endpoint is configured
    # ------------------------------------------------------------------
    provider_config = None
    if settings.AZURE_OPENAI_ENDPOINT and "your-" not in settings.AZURE_OPENAI_ENDPOINT:
        azure_section: dict = {"api_version": settings.AZURE_OPENAI_API_VERSION}
        # If a tenant ID is known, include it so the Copilot CLI / SDK can
        # request a token scoped to the correct Azure AD tenant.  This prevents
        # the "token tenant does not match resource tenant" error that occurs on
        # Windows when DefaultAzureCredential picks up a cached token from a
        # different Active Directory tenant (e.g. the Microsoft corporate tenant).
        if settings.AZURE_AD_TENANT_ID:
            azure_section["tenant_id"] = settings.AZURE_AD_TENANT_ID

        provider_config = {
            "type": "azure",
            "base_url": settings.AZURE_OPENAI_ENDPOINT,
            "azure": azure_section,
        }
        if settings.AZURE_OPENAI_KEY:
            provider_config["api_key"] = settings.AZURE_OPENAI_KEY
        elif platform.system() == "Windows":
            # On Windows, DefaultAzureCredential may silently pick up a cached
            # token from the Microsoft corporate tenant instead of the tenant
            # that owns the Azure OpenAI resource, resulting in a 400 "token
            # tenant does not match resource tenant" error.  Warn early so the
            # user can act before reaching the probe step.
            logger.warning(
                "BYOK Azure OpenAI is configured without an API key on Windows — "
                "if the preflight check fails with a tenant-mismatch error, set "
                "AZURE_OPENAI_KEY or run 'az login --tenant <your-tenant-id>' "
                "and ensure AZURE_AD_TENANT_ID is set in your .env."
            )

    
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
        working_directory=os.path.expanduser(settings.CLI_WORKING_DIRECTORY) if settings.CLI_WORKING_DIRECTORY else None,
        skill_directories=skills_manager.get_skill_directories(),
    )

    # Preflight — auth-only connectivity check.  Purely informational: the
    # result is cached on session_factory.health for the /health endpoint but
    # NEVER used to gate session creation.  Real sessions surface their own
    # errors (wrong model, expired token, org policy) when they are created.
    try:
        result = await session_factory.verify(full_probe=False)
        if result.healthy:
            logger.info(
                "Copilot SDK preflight check passed: %s", result.summary()
            )
        else:
            logger.warning(
                "Copilot SDK preflight: %s — sessions will be attempted "
                "anyway and will fail with a specific error if the CLI is "
                "misconfigured: %s",
                result.summary(),
                result.error,
            )
    except Exception as exc:
        logger.warning(
            "Copilot SDK preflight check raised an exception — sessions will "
            "be attempted anyway: %s",
            exc,
        )

    app.state.session_factory = session_factory
    
    # ------------------------------------------------------------------
    # Session store
    # ------------------------------------------------------------------
    session_store = SessionStore(
        storage_manager=app_storage_manager,
    )
    app.state.session_store = session_store

    # ------------------------------------------------------------------
    # Preferences store
    # ------------------------------------------------------------------
    from app.store.preferences_store import PreferencesStore

    preferences_store = PreferencesStore(storage_manager=app_storage_manager)
    app.state.preferences_store = preferences_store

    # ------------------------------------------------------------------
    # Ensure agent-outputs blob container exists
    # ------------------------------------------------------------------
    try:
        await app_storage_connector.ensure_initialized()
        await app_storage_connector.ensure_container_exists(
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
    # Custom Agent Management — AgentStore + DynamicAgentRegistry
    # ------------------------------------------------------------------
    from app.agents.dynamic_registry import DynamicAgentRegistry
    from app.store.agent_store import AgentStore

    agent_store = AgentStore(
        storage_manager=app_storage_manager,
    )
    app.state.agent_store = agent_store

    dynamic_registry = DynamicAgentRegistry(
        agent_store=agent_store, 
        cache_ttl_seconds=settings.DYNAMIC_REGISTRY_CACHE_TTL_SECONDS,
        prompt_store=prompt_store,
        )
    app.state.dynamic_registry = dynamic_registry
    
    # ------------------------------------------------------------------
    # Approval Manager
    # ------------------------------------------------------------------
    from app.services.approval_manager import ApprovalManager

    approval_manager = ApprovalManager(
        timeout_seconds=settings.APPROVAL_TIMEOUT_SECONDS,
    )
    app.state.approval_manager = approval_manager

    # ------------------------------------------------------------------
    # PersistentAgentService (main agent orchestration service, used by API routes) — depends on session factory, store, approval manager, and dynamic registry
    # ------------------------------------------------------------------
    from app.services.persistent_agent_service import PersistentAgentService

    # Load system prompt from store (respects any prior customisation)
    try:
        active_system_prompt = await prompt_store.get_system_prompt_text()
    except Exception:
        from app.prompts.system_prompt import CONTELLIGENCE_AGENT_SYSTEM_PROMPT
        active_system_prompt = CONTELLIGENCE_AGENT_SYSTEM_PROMPT
        logger.warning("Failed to load system prompt from store — using built-in default.")

    agent_service = PersistentAgentService(
        session_factory=session_factory,
        session_store=session_store,
        system_prompt=active_system_prompt,
        blob_connector=app_storage_connector,
        outputs_container=settings.AGENT_OUTPUTS_CONTAINER,
        large_result_threshold=settings.LARGE_RESULT_THRESHOLD_KB * 1024,
        approval_manager=approval_manager,
        dynamic_registry=dynamic_registry,
        skills_manager=skills_manager,
        preferences_store=preferences_store,
        settings=settings,
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

            await app_storage_manager.ensure_initialized()
            cache_container = app_storage_manager.get_container("extraction-cache")
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
    if settings.KEY_VAULT_ENDPOINT:
        try:
            from azure.identity.aio import DefaultAzureCredential
            from azure.keyvault.secrets.aio import SecretClient

            from app.auth.token_manager import TokenManager

            kv_credential = DefaultAzureCredential()
            kv_client = SecretClient(
                vault_url=settings.KEY_VAULT_ENDPOINT,
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

        await app_storage_manager.ensure_initialized()
        from app.utils.instance import get_instance_id

        retention_policy = RetentionPolicy(
            session_retention_days=settings.SESSION_RETENTION_DAYS,
            blob_archive_days=settings.BLOB_ARCHIVE_DAYS,
            blob_delete_days=settings.BLOB_DELETE_DAYS,
        )
        retention_cleanup = RetentionCleanup(
            session_store=session_store,
            blob_connector=app_storage_connector,
            retention_policy=retention_policy,
        )

        # Schedule Store
        schedule_store = ScheduleStore(
            storage_manager=app_storage_manager,
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
            storage_manager=app_storage_manager,
            instance_id=get_instance_id(),
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
    shared_dir = settings.AGENT_SHARED_SKILLS_DIRECTORY or '(not configured)'
    cli_skills_dir = settings.CLI_SHARED_SKILLS_DIRECTORY or '(not configured)'
    logger.info(f"Shared skills directory: {shared_dir}")
    logger.info(f"CLI shared skills directory: {cli_skills_dir}")

    # ------------------------------------------------------------------
    # Health Watchdog — periodically probe connectors and recycle stale
    # ones so the backend self-heals after laptop sleep / network blips.
    # ------------------------------------------------------------------
    asyncio.create_task(_health_watchdog(app))
    logger.info("Health watchdog background task started.")

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

async def _health_watchdog(app: FastAPI) -> None:
    """Background task that probes connectors and recycles stale ones.

    Runs every 60 seconds.  After a laptop-sleep / network outage this
    detects dead connection pools and reinitialises them so the next user
    request succeeds without a manual restart.
    """
    settings = get_settings()
    is_local = settings.STORAGE_MODE == "local"
    interval = 60  # seconds

    while True:
        await asyncio.sleep(interval)
        try:
            # --- Cosmos DB / SQLite health probe ---
            storage_manager = getattr(app.state, "app_storage_manager", None)
            if storage_manager is not None and not is_local:
                # For Azure mode, attempt a lightweight query to verify
                # the Cosmos connection pool is alive.
                cosmos_connector = getattr(storage_manager, "_cosmos_connector", None)
                if cosmos_connector is not None:
                    try:
                        db_name = cosmos_connector._resolve_database(None)
                        db_client = cosmos_connector._client.get_database_client(db_name)
                        await db_client.read()
                    except Exception:
                        logger.warning(
                            "[health-watchdog] Cosmos DB probe failed — recycling client.",
                            exc_info=True,
                        )
                        await _recycle_cosmos_connector(cosmos_connector)

            # --- Blob Storage health probe (Azure mode only) ---
            blob_connector = getattr(app.state, "app_storage_connector", None)
            if blob_connector is not None and not is_local:
                try:
                    await blob_connector.list_containers()
                except Exception:
                    logger.warning(
                        "[health-watchdog] Blob Storage probe failed — recycling client.",
                        exc_info=True,
                    )
                    await _recycle_blob_connector(blob_connector)

            # --- Copilot SDK client factory probe ---
            client_factory = getattr(app.state, "client_factory", None)
            if client_factory is not None:
                try:
                    client = client_factory._client
                    if client is None:
                        raise RuntimeError("Copilot client is None")
                except Exception:
                    logger.warning(
                        "[health-watchdog] Copilot client unavailable — attempting restart.",
                        exc_info=True,
                    )
                    try:
                        await client_factory.start()
                        logger.info("[health-watchdog] Copilot client restarted.")
                    except Exception:
                        logger.error(
                            "[health-watchdog] Copilot client restart failed.",
                            exc_info=True,
                        )

        except Exception:
            logger.error("[health-watchdog] Unexpected error in watchdog loop.", exc_info=True)


async def _recycle_cosmos_connector(connector: object) -> None:
    """Close and re-initialise a CosmosConnectorAdapter."""
    try:
        await connector.close()  # type: ignore[union-attr]
    except Exception:
        logger.debug("[health-watchdog] Error closing Cosmos connector.", exc_info=True)
    connector._client = None  # type: ignore[attr-defined]
    connector._credential = None  # type: ignore[attr-defined]
    await connector.ensure_initialized()  # type: ignore[union-attr]
    logger.info("[health-watchdog] Cosmos connector recycled.")


async def _recycle_blob_connector(connector: object) -> None:
    """Close and re-initialise a BlobConnectorAdapter."""
    try:
        await connector.close()  # type: ignore[union-attr]
    except Exception:
        logger.debug("[health-watchdog] Error closing Blob connector.", exc_info=True)
    connector._client = None  # type: ignore[attr-defined]
    connector._credential = None  # type: ignore[attr-defined]
    await connector.ensure_initialized()  # type: ignore[union-attr]
    logger.info("[health-watchdog] Blob connector recycled.")


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
        "storage_manager",
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
