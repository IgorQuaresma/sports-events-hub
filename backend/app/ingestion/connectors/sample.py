"""Loads `EventCandidate` objects from a JSON fixture file (demo data / offline development)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.schemas.candidate import EventCandidate

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures"


class SampleFixtureConnector:
    key = "sample_fixture"

    def __init__(self, config: dict[str, Any]) -> None:
        self.path = Path(
            config.get("path") or FIXTURES_DIR / config.get("fixture", "sample_events.json")
        )

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        yield DiscoveredItem(url=f"fixture://{self.path.name}")

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        return RawDocument(
            url=item.url,
            body=self.path.read_bytes(),
            fetched_at=datetime.now(UTC),
            http_status=200,
            content_type="application/json",
        )

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        items = json.loads(raw.body)
        return [
            ParseResult(candidate=EventCandidate.model_validate(it), method="fixture")
            for it in items
        ]
