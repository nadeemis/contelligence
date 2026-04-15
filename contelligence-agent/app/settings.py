from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):

    # ── 1. App Operational Config ─────────────────────────────────────

    # Server
    API_VERSION: str = "v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8081
    LOG_LEVEL: str = "DEBUG"
    SESSION_TIMEOUT_MINUTES: int = 60

    # Storage mode: "azure" for cloud deployment, "local" for standalone desktop
    STORAGE_MODE: str = "local"
    LOCAL_DATA_DIR: str = ""       # Local data directory (SQLite DB, blobs, logs)

    # Working directory & skills
    CLI_WORKING_DIRECTORY: str = ""      # CLI working directory (e.g. /contelligence in Docker)
    # Single writable path where all skills (built-in + user-created) are
    # materialized on disk.  The Copilot SDK and CLI discover skills from
    # this directory.  Docker: /shared/skills  |  Electron: <userData>/skills
    # When empty, skills are only stored in Cosmos/Blob and the SDK uses the
    # built-in skills dir.
    AGENT_SHARED_SKILLS_DIRECTORY: str = ""
    CLI_SHARED_SKILLS_DIRECTORY: str = ""
    COPILOT_CLI_ARGS: str = ""  # Additional CLI args for CopilotClient subprocess (e.g. ["--verbose"]), comma-separated when set via env var
    
    @field_validator("AGENT_SHARED_SKILLS_DIRECTORY", mode="after")
    @classmethod
    def _expand_shared_skills_dir(cls, v: str) -> str:
        return os.path.expanduser(v) if v else v
    
    @field_validator("COPILOT_CLI_ARGS", mode="after")
    @classmethod
    def _expand_copilot_cli_args(cls, v: str) -> list[str]:
        return [v.strip() for v in v.split(",")] if v else []

    # RBAC
    AUTH_ENABLED: bool = False
    AZURE_AD_TENANT_ID: str = ""
    AZURE_AD_CLIENT_ID: str = ""

    # Persistent Sessions
    LARGE_RESULT_THRESHOLD_KB: int = 50           # Tool result size threshold for blob offloading (KB)
    AGENT_OUTPUTS_CONTAINER: str = "agent-outputs"  # Blob container for session outputs

    # Model Fallback
    DEFAULT_MODEL_FALLBACK_ENABLED: bool = True     # Enable model resolution chain

    # Session Quotas
    SESSION_MAX_TOOL_CALLS: int = 200
    SESSION_MAX_DOCUMENTS: int = 100
    SESSION_MAX_TOKENS: int = 500_000

    # Rate Limiting
    RATE_LIMIT_OPENAI_RPM: int = 60
    RATE_LIMIT_DOC_INTEL_RPM: int = 15

    # Extraction Caching
    CACHE_ENABLED: bool = True
    CACHE_TTL_DAYS: int = 7

    # Session Retention
    SESSION_RETENTION_DAYS: int = 90
    BLOB_ARCHIVE_DAYS: int = 90
    BLOB_DELETE_DAYS: int = 730

    # Approval
    APPROVAL_TIMEOUT_SECONDS: int = 300           # 5-minute default timeout

    # Agent Registry Caching
    DYNAMIC_REGISTRY_CACHE_TTL_SECONDS: int = 60  # TTL for caching user-created agents from Cosmos DB

    # Horizontal Scaling
    MAX_REPLICAS: int = 10

    # Scheduling Engine
    AGENT_BASE_URL: str = "http://localhost:8060"  # Base URL for webhook URLs
    SCHEDULE_AUTO_PAUSE_THRESHOLD: int = 3         # Consecutive failures before auto-pause
    SCHEDULER_MISFIRE_GRACE_TIME: int = 28_800     # APScheduler misfire grace (seconds) — 8 h to survive sleep

    # ── 2. Service Endpoints & Keys ───────────────────────────────────

    # Application Storage — Cosmos DB (Azure mode)
    APP_STORAGE_DATABASE: str = "contelligence"    # Cosmos DB database name or SQLite file name (without .db)
    APP_STORAGE_COSMOS_ENDPOINT: str = ""
    APP_STORAGE_COSMOS_KEY: str = ""

    # Application Storage — Blob Storage (Azure mode)
    APP_AZURE_STORAGE_ACCOUNT_NAME: str = ""
    APP_AZURE_STORAGE_CREDENTIAL_TYPE: str = "default_azure_credential"
    APP_AZURE_STORAGE_KEY: str = ""

    # Key Vault
    KEY_VAULT_ENDPOINT: str = ""

    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4.1"
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT: str = "text-embedding-3-large"

    # GitHub Copilot SDK
    GITHUB_COPILOT_TOKEN: str | None = None        # PAT with 'copilot' scope (also settable via web UI)
    COPILOT_CLI_PATH: str = "copilot"
    COPILOT_CLI_URL: str = ""
    COPILOT_MODEL: str = "claude-opus-4.6"

    # MCP Server (Azure tools sidecar)
    AZURE_MCP_SERVER_URL: str = ""                 # Empty = stdio mode; set URL for HTTP mode
    AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT: str = "false"
    APPLICATIONINSIGHTS_CONNECTION_STRING: str = ""

    # Azure Document Intelligence
    AZURE_DOC_INTELLIGENCE_ENDPOINT: str = ""
    AZURE_DOC_INTELLIGENCE_KEY: str = ""

    # Azure Speech Services
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""

    # Azure DevOps
    AZURE_DEVOPS_DEFAULT_ORG: str = ""             # Azure DevOps organization name
    AZURE_DEVOPS_DEFAULT_PROJECT: str = ""         # Default project name (optional)
    AZURE_DEVOPS_PAT: str = ""                     # Personal Access Token (optional, takes priority over Entra ID)
    AZURE_DEVOPS_TENANT_ID: str = ""               # Entra ID tenant (optional, for multi-tenant)

    # Power BI
    POWERBI_WORKSPACE_ID: str = ""                 # Default Power BI workspace (group) ID
    POWERBI_TENANT_ID: str = ""                    # Entra ID tenant for Power BI auth
    POWERBI_CLIENT_ID: str = ""                    # Service principal client ID (optional)
    POWERBI_CLIENT_SECRET: str = ""                # Service principal client secret (optional)

    # SharePoint
    SHAREPOINT_SITE_URL: str = ""                  # e.g. https://contoso.sharepoint.com/sites/team
    SHAREPOINT_ACCESS_TOKEN: str = ""              # Delegated access token (optional, takes priority)

    # Microsoft Graph / Teams
    MSGRAPH_TENANT_ID: str = ""                    # Entra ID tenant for Graph API auth
    MSGRAPH_CLIENT_ID: str = ""                    # App registration client ID (optional)
    MSGRAPH_CLIENT_SECRET: str = ""                # App registration client secret (optional)
    MSGRAPH_ACCESS_TOKEN: str = ""                 # Delegated access token (optional, takes priority)
    MSGRAPH_USER_ID: str = ""                      # Target user ID / UPN for app-only flows

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
    
    def app_data_dir(self) -> Path:
        """Return a platform-appropriate app data directory."""
        data_dir = Path(self.LOCAL_DATA_DIR) if self.LOCAL_DATA_DIR else None
        if data_dir is not None:
            return data_dir
        
        return Path.home() / ".contelligence"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
