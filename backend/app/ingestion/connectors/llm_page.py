"""LLM extraction connector for organizer pages without structured data.

Config: {"urls": [...], "sport_slug": "triathlon", "country": "DE"}
Requires ANTHROPIC_API_KEY. Confidence = share of evidence quotes found verbatim in the page;
below 0.8 the record is stored but flagged (review queue planned, plan §7.3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.ai.gateway import extract_event_llm, llm_available, verify_evidence
from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument


def page_text(html: bytes) -> str:
    tree = HTMLParser(html)
    for sel in ("script", "style", "noscript", "svg", "nav", "footer", "header", "iframe"):
        for n in tree.css(sel):
            n.decompose()
    body = tree.body or tree.root
    text = body.text(separator="\n", strip=True) if body else ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


class LlmPageConnector:
    key = "llm_page"

    def __init__(self, config: dict[str, Any]) -> None:
        self.urls: list[str] = config.get("urls", [])
        self.sport = config.get("sport_slug")

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        if not llm_available():
            raise RuntimeError("llm_page connector needs ANTHROPIC_API_KEY")
        for u in self.urls:
            yield DiscoveredItem(url=u)

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        return await fetcher.get(item.url)

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        text = page_text(raw.body)
        if len(text) < 200:
            return []
        cand = await extract_event_llm(text, raw.url, self.sport)
        if self.sport:
            cand.sport_slug = self.sport
        conf = verify_evidence(cand, text)
        return [ParseResult(candidate=cand, method="llm", confidence=conf)]
