
import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

async def resolve_github_token(key_vault_url: str) -> str:
    """Resolve the GitHub PAT from Azure Key Vault.

    Uses ``DefaultAzureCredential`` so the Container App's managed identity
    (production) or Azure CLI credentials (development) are used
    automatically.

    Returns an empty string if the secret cannot be read — the caller
    should log a warning and continue without the GitHub MCP server.
    """
    try:
        from azure.identity.aio import DefaultAzureCredential
        from azure.keyvault.secrets.aio import SecretClient

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=key_vault_url, credential=credential)
        try:
            secret = await client.get_secret("github-copilot-token")
            return secret.value or ""
        finally:
            await client.close()
            await credential.close()
    except Exception:
        logger.warning(
            "Could not resolve GitHub PAT from Key Vault (%s). "
            "GitHub MCP server will be unavailable.",
            key_vault_url,
            exc_info=True,
        )
        return ""
