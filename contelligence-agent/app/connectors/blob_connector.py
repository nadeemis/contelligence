from __future__ import annotations

import logging
from typing import Any

from app.connectors.blob_types import BlobInfo, BlobProperties

logger = logging.getLogger(f"contelligence-agent.{__name__}")


class BlobConnectorAdapter:
    """Thin async wrapper around Azure Blob Storage SDK clients."""

    def __init__(
        self,
        account_name: str,
        credential_type: str = "default_azure_credential",
        account_key: str = "",
    ) -> None:
        self._account_name = account_name
        self._credential_type = credential_type
        self._account_key = account_key
        self._client = None
        self._credential = None

    async def ensure_initialized(self) -> None:
        if self._client is not None:
            return
        from azure.storage.blob.aio import BlobServiceClient

        account_url = f"https://{self._account_name}.blob.core.windows.net"
        if self._account_key:
            self._client = BlobServiceClient(
                account_url=account_url, credential=self._account_key
            )
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
            self._client = BlobServiceClient(
                account_url=account_url, credential=self._credential
            )

    async def list_blobs(
        self,
        container: str,
        prefix: str | None = None,
        max_results: int = 100,
    ) -> list[BlobInfo]:
        await self.ensure_initialized()
        container_client = self._client.get_container_client(container)
        blobs: list[BlobInfo] = []
        async for blob in container_client.list_blobs(
            name_starts_with=prefix, results_per_page=max_results
        ):
            blobs.append(
                BlobInfo(
                    name=blob.name,
                    size=blob.size or 0,
                    content_type=(
                        blob.content_settings.content_type
                        if blob.content_settings
                        else None
                    ),
                )
            )
            if len(blobs) >= max_results:
                break
        return blobs

    async def download_blob(self, container: str, path: str) -> bytes:
        await self.ensure_initialized()
        blob_client = self._client.get_blob_client(container, path)
        stream = await blob_client.download_blob()
        return await stream.readall()

    async def upload_blob(
        self,
        container: str,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        await self.ensure_initialized()
        from azure.storage.blob import ContentSettings

        blob_client = self._client.get_blob_client(container, path)
        await blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    async def get_blob_properties(
        self, container: str, path: str
    ) -> BlobProperties:
        await self.ensure_initialized()
        blob_client = self._client.get_blob_client(container, path)
        props = await blob_client.get_blob_properties()
        return BlobProperties(
            name=path,
            size=props.size or 0,
            content_type=(
                props.content_settings.content_type
                if props.content_settings
                else None
            ),
            metadata=dict(props.metadata) if props.metadata else {},
        )

    async def list_containers(self) -> list[Any]:
        await self.ensure_initialized()
        containers = []
        async for container in self._client.list_containers():
            containers.append(container)
        return containers
    
    async def ensure_container_exists(self, container_name: str) -> None:
        """Create a blob container if it does not already exist.

        Idempotent — safe to call on every application startup.
        """
        await self.ensure_initialized()
        container_client = self._client.get_container_client(container_name)
        try:
            await container_client.create_container()
            logger.info(f"Created blob container '{container_name}'.")
        except Exception as exc:
            # ResourceExistsError or similar — container already exists
            if "ContainerAlreadyExists" in str(exc) or "409" in str(exc):
                logger.debug(f"Blob container '{container_name}' already exists.")
            else:
                raise

    async def delete_blob(self, container: str, path: str) -> None:
        """Delete a single blob by container and path."""
        await self.ensure_initialized()
        blob_client = self._client.get_blob_client(container, path)
        await blob_client.delete_blob()

    async def delete_prefix(
        self,
        container_name: str,
        prefix: str,
    ) -> int:
        """Delete all blobs under a prefix.  Returns the count of deleted blobs.

        Used by the retention cleanup to purge output blobs for expired
        sessions.
        """
        await self.ensure_initialized()
        container_client = self._client.get_container_client(container_name)
        count = 0
        async for blob in container_client.list_blobs(name_starts_with=prefix):
            await container_client.delete_blob(blob.name)
            count += 1
        return count

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        if self._credential is not None and hasattr(self._credential, "close"):
            await self._credential.close()
            self._credential = None
