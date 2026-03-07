from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    # Azure Storage
    AZURE_STORAGE_ACCOUNT_NAME: str = ""
    AZURE_STORAGE_CREDENTIAL_TYPE: str = "default_azure_credential"
    AZURE_STORAGE_KEY: str = ""

    # Azure Search
    AZURE_SEARCH_ACCOUNT_NAME: str = ""
    AZURE_SEARCH_CREDENTIAL_TYPE: str = "default_azure_credential"
    AZURE_SEARCH_API_KEY: str = ""
    AZURE_SEARCH_API_VERSION: str = "2024-07-01"

    # Azure Cosmos DB
    AZURE_COSMOS_ENDPOINT: str = ""
    AZURE_COSMOS_KEY: str = ""
    AZURE_COSMOS_DATABASE: str = "contelligence-agent"

    # Azure Document Intelligence
    AZURE_DOC_INTELLIGENCE_ENDPOINT: str = ""
    AZURE_DOC_INTELLIGENCE_KEY: str = ""

    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"

    # GitHub Copilot SDK
    GITHUB_COPILOT_TOKEN: str | None = None  # GitHub Personal Access Token with 'copilot' scope (can also be set via the web UI for easier token rotation)
    COPILOT_CLI_PATH: str = "copilot"
    COPILOT_CLI_URL: str = ""
    COPILOT_MODEL: str = "claude-opus-4.6"

    # Session working directory (used by SDK for tool operations)
    WORKING_DIRECTORY: str = ""

    # Extra skill directories (comma-separated) — merged with built-in skills dir
    EXTRA_SKILLS_DIRECTORIES: str = ""

    # Persistent Sessions
    LARGE_RESULT_THRESHOLD_KB: int = 50           # Tool result size threshold for blob offloading (KB)
    AGENT_OUTPUTS_CONTAINER: str = "agent-outputs"  # Blob container for session outputs

    # Agent Registry Caching
    DYNAMIC_REGISTRY_CACHE_TTL_SECONDS: int = 60  # TTL for caching user-created agents from Cosmos DB
    
    # Server
    API_VERSION: str = "v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8081
    LOG_LEVEL: str = "INFO"
    SESSION_TIMEOUT_MINUTES: int = 60

    # Audio
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""

    # Phase 3 — MCP Server
    AZURE_MCP_SERVER_URL: str = ""                            # Empty = stdio mode; set URL for HTTP mode
    AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT: str = "false"      # Disable Microsoft-collected telemetry
    APPLICATIONINSIGHTS_CONNECTION_STRING: str = ""            # Route MCP telemetry to App Insights
    KEY_VAULT_URL: str = ""                                   # Azure Key Vault for GitHub PAT
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT: str = "text-embedding-3-large"
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4.1"

    # Phase 3 — Approval
    APPROVAL_TIMEOUT_SECONDS: int = 300                       # 5-minute default timeout

    # Phase 4 — RBAC
    AUTH_ENABLED: bool = False
    AZURE_AD_TENANT_ID: str = ""
    AZURE_AD_CLIENT_ID: str = ""

    # Phase 4 — Rate Limiting
    RATE_LIMIT_OPENAI_RPM: int = 60
    RATE_LIMIT_DOC_INTEL_RPM: int = 15

    # Phase 4 — Session Quotas
    SESSION_MAX_TOOL_CALLS: int = 200
    SESSION_MAX_DOCUMENTS: int = 100
    SESSION_MAX_TOKENS: int = 500_000

    # Phase 4 — Extraction Caching
    CACHE_ENABLED: bool = True
    CACHE_TTL_DAYS: int = 7

    # Phase 4 — Session Retention
    SESSION_RETENTION_DAYS: int = 90
    BLOB_ARCHIVE_DAYS: int = 90
    BLOB_DELETE_DAYS: int = 730

    # Phase 4 — Horizontal Scaling
    MAX_REPLICAS: int = 10

    # Phase 5 — Scheduling Engine
    AGENT_BASE_URL: str = "http://localhost:8060"    # Base URL for webhook URLs
    SCHEDULE_AUTO_PAUSE_THRESHOLD: int = 3           # Consecutive failures before auto-pause
    SCHEDULER_MISFIRE_GRACE_TIME: int = 60           # APScheduler misfire grace (seconds)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
