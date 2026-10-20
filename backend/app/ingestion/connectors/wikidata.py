"""Wikidata discovery connector: open (CC0) list of recurring endurance events + official sites.

Wikidata knows *which* events exist (Berlin-Marathon, KnappenMan, Mozart 100, ...) and their
official websites and coordinates, but rarely the next edition's date. So this connector:

  1. runs one SPARQL query against the Wikidata Query Service (WDQS) for events in the
     configured countries that have an official website (P856),
  2. fetches each official website (robots.txt respected, like any page),
  3. extracts schema.org Event JSON-LD from it (and, optionally, falls back to LLM extraction),
  4. fills missing coordinates/country from Wikidata.

Pages without structured data produce nothing — dates are never guessed.

WDQS policy: descriptive User-Agent with contact (set CONTACT_EMAIL), modest query volume.
Its robots.txt targets crawlers; the SPARQL endpoint itself is the documented API.

Config (all optional):
  {"countries": ["DE", "AT", "CH"],
   "max_events": 200,
   "llm_fallback": false,        # use Claude on sites without JSON-LD (needs ANTHROPIC_API_KEY)
   "endpoint": "https://query.wikidata.org/sparql"}
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from urllib.parse import urlencode, urlparse

from pydantic import HttpUrl

from app.ingestion.base import DiscoveredItem, Fetcher, ParseResult, RawDocument
from app.ingestion.connectors.jsonld import (
    candidate_from_node,
    extract_jsonld_blocks,
    iter_event_nodes,
)
from app.ingestion.fetcher import get_json

log = logging.getLogger("ingest.wikidata")

ENDPOINT = "https://query.wikidata.org/sparql"

# Wikidata class (P31 value) → taxonomy sport. Verified QIDs (2026-10).
TYPE_TO_SPORT: dict[str, str] = {
    "Q40244": "running",  # marathon
    "Q215677": "running",  # half marathon
    "Q26303": "running",  # ultramarathon
    "Q2093999": "trail-running",  # trail running
    "Q10980": "triathlon",  # triathlon
    "Q429006": "triathlon",  # duathlon
    "Q1338800": "triathlon",  # Ironman Triathlon (series)
    "Q1750982": "cycling",  # cyclosportive
    "Q631004": "swimming",  # open water swimming
    "Q4703797": "ocr",  # obstacle racing
}
COUNTRY_QIDS = {"DE": "Q183", "AT": "Q40", "CH": "Q39", "IT": "Q38", "FR": "Q142", "NL": "Q55"}
# when an item has several classes, the more specific sport wins
SPORT_PRIORITY = ["ocr", "triathlon", "trail-running", "swimming", "cycling", "running"]
_POINT = re.compile(r"Point\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)")


def build_query(countries: list[str]) -> str:
    types = " ".join(f'("{sport}" wd:{q})' for q, sport in TYPE_TO_SPORT.items())
    places = " ".join(f'(wd:{COUNTRY_QIDS[c]} "{c}")' for c in countries if c in COUNTRY_QIDS)
    return f"""
SELECT ?item ?itemLabel ?web ?coord ?cc ?sport WHERE {{
  VALUES (?sport ?type) {{ {types} }}
  VALUES (?country ?cc) {{ {places} }}
  ?item wdt:P31 ?type ; wdt:P17 ?country ; wdt:P856 ?web .
  FILTER NOT EXISTS {{ ?item wdt:P576 ?dissolved }}
  OPTIONAL {{ ?item wdt:P625 ?coord }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
}}"""


def _website_rank(url: str) -> tuple[int, int]:
    """Prefer https and the shortest (language-neutral) URL among several P856 values."""
    p = urlparse(url)
    lang_path = bool(re.match(r"^/(fr|it|en|es|nl)(/|$)", p.path))
    return (0 if p.scheme == "https" else 1, int(lang_path) * 100 + len(url))


def rows_to_items(bindings: list[dict]) -> list[dict[str, Any]]:
    """Collapse SPARQL rows (one per item × website × class) into one record per item."""
    items: dict[str, dict[str, Any]] = {}
    for b in bindings:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        web = b.get("web", {}).get("value", "")
        if not web.startswith(("http://", "https://")):
            continue
        rec = items.setdefault(
            qid,
            {
                "qid": qid,
                "label": b.get("itemLabel", {}).get("value", qid),
                "websites": set(),
                "sports": set(),
                "country": b.get("cc", {}).get("value"),
                "lat": None,
                "lon": None,
            },
        )
        rec["websites"].add(web)
        rec["sports"].add(b.get("sport", {}).get("value"))
        m = _POINT.match(b.get("coord", {}).get("value", ""))
        if m and rec["lat"] is None:
            rec["lon"], rec["lat"] = float(m.group(1)), float(m.group(2))
    out = []
    for rec in items.values():
        if re.fullmatch(r"Q\d+", rec["label"]):
            rec["label"] = None  # no label in de/en
        rec["website"] = min(rec.pop("websites"), key=_website_rank)
        sports = rec.pop("sports")
        rec["sport"] = next((s for s in SPORT_PRIORITY if s in sports), "running")
        out.append(rec)
    return sorted(out, key=lambda r: r["qid"])


class WikidataConnector:
    key = "wikidata"

    def __init__(self, config: dict[str, Any]) -> None:
        self.countries = [c.upper() for c in config.get("countries", ["DE", "AT", "CH"])]
        self.max_events = int(config.get("max_events", 200))
        self.llm_fallback = bool(config.get("llm_fallback", False))
        self.endpoint = str(config.get("endpoint", ENDPOINT))
        self._hints: dict[str, dict[str, Any]] = {}

    async def discover(self, fetcher: Fetcher) -> AsyncIterator[DiscoveredItem]:
        url = f"{self.endpoint}?{urlencode({'query': build_query(self.countries)})}"
        _raw, body = await get_json(
            fetcher,
            url,
            headers={"Accept": "application/sparql-results+json"},
            check_robots=False,  # documented API, see module docstring
        )
        items = rows_to_items(((body or {}).get("results") or {}).get("bindings") or [])
        log.info("wikidata: %d events with official websites", len(items))
        for rec in items[: self.max_events]:
            yield DiscoveredItem(url=rec["website"], external_id=rec["qid"], hint=rec)

    async def fetch(self, item: DiscoveredItem, fetcher: Fetcher) -> RawDocument:
        raw = await fetcher.get(item.url)
        raw.external_id = item.external_id
        # remember Wikidata facts for parse() (also under the post-redirect URL)
        self._hints[raw.url] = self._hints[item.url] = item.hint
        return raw

    async def parse(self, raw: RawDocument) -> list[ParseResult]:
        hint = self._hints.get(raw.url, {})
        sport = hint.get("sport", "running")
        if raw.http_status is not None and raw.http_status >= 400:
            return []
        results: list[ParseResult] = []
        for block in extract_jsonld_blocks(raw.body):
            for node in iter_event_nodes(block):
                cand = candidate_from_node(node, raw.url, sport, None)
                if cand is None or cand.start_date < date.today():
                    continue
                if cand.location.lat is None and hint.get("lat") is not None:
                    cand.location.lat, cand.location.lon = hint["lat"], hint["lon"]
                cand.location.country = cand.location.country or hint.get("country")
                cand.website = cand.website or HttpUrl(raw.url)
                results.append(ParseResult(candidate=cand, method="jsonld", confidence=0.85))
        if not results and self.llm_fallback:
            results = await self._llm_extract(raw, sport, hint)
        return results

    async def _llm_extract(
        self, raw: RawDocument, sport: str, hint: dict[str, Any]
    ) -> list[ParseResult]:
        from app.ai.gateway import extract_event_llm, llm_available, verify_evidence
        from app.ingestion.connectors.llm_page import page_text

        if not llm_available():
            return []
        text = page_text(raw.body)
        if len(text) < 200:
            return []
        cand = await extract_event_llm(text, raw.url, sport)
        if cand.start_date < date.today():
            return []
        cand.sport_slug = sport
        cand.location.country = cand.location.country or hint.get("country")
        if cand.location.lat is None and hint.get("lat") is not None:
            cand.location.lat, cand.location.lon = hint["lat"], hint["lon"]
        return [ParseResult(candidate=cand, method="llm", confidence=verify_evidence(cand, text))]
