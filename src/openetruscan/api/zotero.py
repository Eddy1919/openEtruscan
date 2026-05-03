import httpx
from typing import Any
import logging

logger = logging.getLogger("openetruscan")

class ZoteroClient:
    """Client for fetching bibliographical data from Zotero API."""

    def __init__(
        self,
        group_id: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None
    ):
        self.group_id = group_id
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self.base_url = f"https://api.zotero.org/groups/{group_id}/items"

    async def get_item_csl(self, item_key: str) -> dict[str, Any] | None:
        """Fetch an item in CSL-JSON format."""
        headers = {}
        if self.api_key:
            headers["Zotero-API-Key"] = self.api_key

        try:
            url = f"{self.base_url}/{item_key}"
            params = {"format": "csljson"}
            
            response = await self.client.get(url, params=params, headers=headers)
            
            if response.status_code == 404:
                logger.warning(f"Zotero item {item_key} not found in group {self.group_id}")
                return None
                
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Zotero API error for item {item_key}: {e}")
            return None

    async def get_item_citation(self, item_key: str, style: str = "apa") -> str | None:
        """Fetch a rendered citation string."""
        headers = {}
        if self.api_key:
            headers["Zotero-API-Key"] = self.api_key

        try:
            url = f"{self.base_url}/{item_key}"
            params = {"format": "bib", "style": style}
            
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            # format=bib returns a full HTML bibliography block usually.
            # For a single item, we might just want the string.
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"Zotero API error for item {item_key}: {e}")
            return None
