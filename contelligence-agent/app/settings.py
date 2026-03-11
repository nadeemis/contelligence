from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    # Storage mode: "azure" for cloud deployment, "local" for standalone desktop
    STORAGE_MODE: str = "azure"
    LOCAL_DATA_DIR: str = ""       # Local data directory (SQLite DB, blobs, logs)
    LOCAL_BLOBS_DIR: str = ""      # Local blob storage directory (defaults to LOCAL_DATA_DIR/blobs)

    # Application storage (Azure or local) — used for session data, agent outputs, and optionally by tools
    # If Azure, uses Cosmos DB for structured data and Blob Storage for large unstructured data; if local, uses SQLite and filesystem blobs
    # If Azure, APP_STORAGE_ENDPOINT and APP_STORAGE_DATABASE specify the Cosmos DB account and database; 
    # if local, LOCAL_DATA_DIR specifies the SQLite file location and LOCAL_BLOBS_DIR specifies the blob storage directory
    # Common for both modes:
    APP_STORAGE_DATABASE: str = "contelligence"  # Cosmos DB database name or SQLite file name (without .db extension)
    # Specific to Azure mode:    
    APP_STORAGE_COSMOS_ENDPOINT: str = ""
    APP_STORAGE_COSMOS_KEY: str = ""

    # Azure Storage
    # Used for app storage blobs and optionally by tools that need blob storage (e.g. for large tool outputs or file uploads)
    APP_AZURE_STORAGE_ACCOUNT_NAME: str = ""
    APP_AZURE_STORAGE_CREDENTIAL_TYPE: str = "default_azure_credential"
    APP_AZURE_STORAGE_KEY: str = ""

    # Azure Cosmos DB
    # AZURE_COSMOS_ENDPOINT: str = ""
    # AZURE_COSMOS_KEY: str = ""
    # AZURE_COSMOS_DATABASE: str = ""

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

    # Keyvault for Github Token and other secrets
    KEY_VAULT_ENDPOINT: str = ""
    
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

    # MCP Server
    AZURE_MCP_SERVER_URL: str = ""                            # Empty = stdio mode; set URL for HTTP mode
    AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT: str = "false"      # Disable Microsoft-collected telemetry
    APPLICATIONINSIGHTS_CONNECTION_STRING: str = ""            # Route MCP telemetry to App Insights
                                  # Azure Key Vault for GitHub PAT
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT: str = "text-embedding-3-large"
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4.1"

    # Approval
    APPROVAL_TIMEOUT_SECONDS: int = 300                       # 5-minute default timeout

    # RBAC
    AUTH_ENABLED: bool = False
    AZURE_AD_TENANT_ID: str = ""
    AZURE_AD_CLIENT_ID: str = ""

    # Rate Limiting
    RATE_LIMIT_OPENAI_RPM: int = 60
    RATE_LIMIT_DOC_INTEL_RPM: int = 15

    # Session Quotas
    SESSION_MAX_TOOL_CALLS: int = 200
    SESSION_MAX_DOCUMENTS: int = 100
    SESSION_MAX_TOKENS: int = 500_000

    # Extraction Caching
    CACHE_ENABLED: bool = True
    CACHE_TTL_DAYS: int = 7

    # Session Retention
    SESSION_RETENTION_DAYS: int = 90
    BLOB_ARCHIVE_DAYS: int = 90
    BLOB_DELETE_DAYS: int = 730

    # Horizontal Scaling
    MAX_REPLICAS: int = 10

    # Azure DevOps
    AZURE_DEVOPS_DEFAULT_ORG: str = ""                       # Azure DevOps organization name
    AZURE_DEVOPS_DEFAULT_PROJECT: str = ""            # Default project name (optional)
    AZURE_DEVOPS_PAT: str = ""                       # Personal Access Token (optional, takes priority over Entra ID)
    AZURE_DEVOPS_TENANT_ID: str = ""                 # Entra ID tenant (optional, for multi-tenant)

    # Power BI
    POWERBI_WORKSPACE_ID: str = ""                    # Default Power BI workspace (group) ID
    POWERBI_TENANT_ID: str = ""                       # Entra ID tenant for Power BI auth
    POWERBI_CLIENT_ID: str = ""                       # Service principal client ID (optional)
    POWERBI_CLIENT_SECRET: str = ""                   # Service principal client secret (optional)

    # Scheduling Engine
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
