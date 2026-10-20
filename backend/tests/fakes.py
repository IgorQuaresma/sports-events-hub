"""Test doubles shared by connector tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.ingestion.base import RawDocument


@dataclass
class Call:
    url: str
    headers: dict[str, str] | None
    secret_params: dict[str, str] | None
    check_robots: bool


@dataclass
class FakeFetcher:
    """Answers every GET with `handler(url) -> (status, body)`; records each call."""

    handler: Callable[[str], tuple[int, Any]]
    calls: list[Call] = field(default_factory=list)

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        secret_params: dict[str, str] | None = None,
        check_robots: bool = True,
    ) -> RawDocument:
        self.calls.append(Call(url, headers, secret_params, check_robots))
        status, body = self.handler(url)
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        return RawDocument(
            url=url, body=payload, fetched_at=datetime.now(UTC), http_status=status
        )
