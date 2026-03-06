from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(f"contelligence-agent.{__name__}")

class OpenAIConnectorAdapter:
    """Thin async wrapper around Azure OpenAI via the ``openai`` SDK.

    Supports both API-key authentication and ``DefaultAzureCredential``
    (token-provider flow).
    """

    def __init__(
        self,
        endpoint: str,
        key: str = "",
        api_version: str = "2024-06-01",
    ) -> None:
        self._endpoint = endpoint
        self._key = key
        self._api_version = api_version
        self._client = None
        self._credential = None  # kept alive for close()

    async def ensure_initialized(self) -> None:
        if self._client is not None:
            return
        from openai import AsyncAzureOpenAI

        if self._key:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._key,
                api_version=self._api_version,
            )
        else:
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

            self._credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                self._credential,
                "https://cognitiveservices.azure.com/.default",
            )
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self._api_version,
            )

    async def generate_embeddings(
        self,
        texts: list[str],
        model: str = "text-embedding-3-large",
        dimensions: int | None = None,
    ) -> dict[str, Any]:
        """Generate embeddings for a list of texts.

        Args:
            texts: Input strings to embed.
            model: Azure OpenAI deployment name.
            dimensions: Desired embedding dimensions (model-dependent).
                Supported by ``text-embedding-3-*`` models. When ``None`` the
                API default for the model is used.

        Returns a dict with:
        - ``model``: the model name used
        - ``count``: number of embeddings produced
        - ``embeddings``: list of ``list[float]`` vectors
        - ``dimensions``: length of each embedding vector
        - ``total_tokens``: total token usage for the request
        """
        await self.ensure_initialized()

        create_kwargs: dict[str, Any] = {"input": texts, "model": model}
        if dimensions is not None:
            create_kwargs["dimensions"] = dimensions

        response = await self._client.embeddings.create(**create_kwargs)

        embeddings: list[list[float]] = [item.embedding for item in response.data]
        actual_dimensions = len(embeddings[0]) if embeddings else 0
        total_tokens = getattr(response.usage, "total_tokens", 0) if response.usage else 0

        logger.info(
            "generate_embeddings model=%s count=%d dimensions=%d tokens=%d",
            model,
            len(embeddings),
            actual_dimensions,
            total_tokens,
        )

        return {
            "model": response.model,
            "count": len(embeddings),
            "embeddings": embeddings,
            "dimensions": actual_dimensions,
            "total_tokens": total_tokens,
        }

    async def get_client(self) -> Any:
        """Return the underlying ``AsyncAzureOpenAI`` client.

        Useful when agent sessions need direct access to the chat-completions
        or other OpenAI endpoints.
        """
        await self.ensure_initialized()
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        if self._credential and hasattr(self._credential, "close"):
            await self._credential.close()
            self._credential = None
