"""Market API client — typed wrapper around market.near.ai REST endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Job:
    job_id: str
    title: str
    description: str
    tags: list[str]
    budget_amount: str | None
    budget_token: str
    job_type: str
    status: str
    bid_count: int
    creator_agent_id: str
    creator_reputation: int
    expires_at: str | None
    max_slots: int
    filled_slots: int
    my_assignments: list[dict] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Job:
        return cls(
            job_id=d["job_id"],
            title=d["title"],
            description=d.get("description", ""),
            tags=d.get("tags", []),
            budget_amount=d.get("budget_amount"),
            budget_token=d.get("budget_token", "NEAR"),
            job_type=d.get("job_type", "standard"),
            status=d.get("status", ""),
            bid_count=d.get("bid_count", 0) or 0,
            creator_agent_id=d.get("creator_agent_id", ""),
            creator_reputation=d.get("creator_reputation", 0) or 0,
            expires_at=d.get("expires_at"),
            max_slots=d.get("max_slots", 1),
            filled_slots=d.get("filled_slots", 0),
            my_assignments=d.get("my_assignments"),
        )

    @property
    def budget_float(self) -> float:
        if not self.budget_amount:
            return 0.0
        try:
            return float(self.budget_amount)
        except (ValueError, TypeError):
            return 0.0


@dataclass
class Bid:
    bid_id: str
    job_id: str
    bidder_agent_id: str
    amount: str
    eta_seconds: int
    proposal: str
    status: str
    created_at: str

    @classmethod
    def from_dict(cls, d: dict) -> Bid:
        return cls(
            bid_id=d["bid_id"],
            job_id=d["job_id"],
            bidder_agent_id=d.get("bidder_agent_id", ""),
            amount=d.get("amount", "0"),
            eta_seconds=d.get("eta_seconds", 86400),
            proposal=d.get("proposal", ""),
            status=d.get("status", ""),
            created_at=d.get("created_at", ""),
        )


class MarketClient:
    """Async HTTP client for market.near.ai v1 API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/v1",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def close(self):
        await self._client.aclose()

    # --- Jobs ---

    async def list_jobs(
        self,
        status: str = "open",
        tags: str | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        job_type: str | None = None,
    ) -> list[Job]:
        params: dict[str, Any] = {"status": status, "sort": sort, "order": order, "limit": limit}
        if tags:
            params["tags"] = tags
        if search:
            params["search"] = search
        if job_type:
            params["job_type"] = job_type
        r = await self._client.get("/jobs", params=params)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        return [Job.from_dict(j) for j in items]

    async def get_job(self, job_id: str) -> Job:
        r = await self._client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        return Job.from_dict(r.json())

    # --- Bids ---

    async def place_bid(self, job_id: str, amount: str, eta_seconds: int, proposal: str) -> Bid:
        r = await self._client.post(
            f"/jobs/{job_id}/bids",
            json={"amount": amount, "eta_seconds": eta_seconds, "proposal": proposal},
        )
        r.raise_for_status()
        return Bid.from_dict(r.json())

    async def my_bids(self) -> list[Bid]:
        r = await self._client.get("/agents/me/bids")
        r.raise_for_status()
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        return [Bid.from_dict(b) for b in items]

    # --- Work ---

    async def submit_deliverable(self, job_id: str, deliverable: str, deliverable_hash: str = "") -> dict:
        body: dict[str, str] = {"deliverable": deliverable}
        if deliverable_hash:
            body["deliverable_hash"] = deliverable_hash
        r = await self._client.post(f"/jobs/{job_id}/submit", json=body)
        r.raise_for_status()
        return r.json()

    async def send_message(self, assignment_id: str, body: str) -> dict:
        r = await self._client.post(f"/assignments/{assignment_id}/messages", json={"body": body})
        r.raise_for_status()
        return r.json()

    async def get_messages(self, assignment_id: str) -> list[dict]:
        r = await self._client.get(f"/assignments/{assignment_id}/messages")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("data", [])

    # --- Competition ---

    async def submit_entry(self, job_id: str, deliverable: str, deliverable_hash: str = "") -> dict:
        body: dict[str, str] = {"deliverable": deliverable}
        if deliverable_hash:
            body["deliverable_hash"] = deliverable_hash
        r = await self._client.post(f"/jobs/{job_id}/entries", json=body)
        r.raise_for_status()
        return r.json()

    # --- Wallet ---

    async def balance(self) -> dict:
        r = await self._client.get("/wallet/balance")
        r.raise_for_status()
        return r.json()

    # --- Profile ---

    async def me(self) -> dict:
        r = await self._client.get("/agents/me")
        r.raise_for_status()
        return r.json()
