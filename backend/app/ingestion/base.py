"""Connector contract. A connector discovers items, fetches raw documents and parses candidates.

`parse()` is pure (no I/O) so it can be unit-tested against saved fixtures.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.schemas.candidate import EventCandidate


@dataclass
class DiscoveredItem:
    url: str
    external_id: str | None = None
    hint: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawDocument:
    url: str  # never contains credentials (see Fetcher.get secret_params)
    body: bytes
    fetched_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    external_id: str | None = None


@dataclass
class ParseResult:
    candidate: EventCandidate
    method: str  # api|jsonld|ical|css|llm|fixture
    confidence: float = 1.0


class Connector(Protocol):
    key: str

    def __init__(self, config: dict[str, Any]) -> None: ...

    def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]: ...

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument: ...

    async def parse(self, raw: RawDocument) -> list[ParseResult]: ...


class Fetcher(Protocol):
    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        secret_params: dict[str, str] | None = None,
        check_robots: bool = True,
    ) -> RawDocument:
        """GET `url`. `secret_params` (e.g. an API key that must travel in the query string)
        are added to the request only — never to `RawDocument.url`, logs or error messages.

        `check_robots=False` is only for documented APIs whose usage policy explicitly invites
        programmatic clients (e.g. the Wikidata Query Service); never for web pages."""
        ...
