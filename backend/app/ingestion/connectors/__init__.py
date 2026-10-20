"""Connector registry. A `source.connector` value maps to a class here."""

from __future__ import annotations

from app.ingestion.connectors.ical import ICalConnector
from app.ingestion.connectors.jsonld import JsonLdConnector
from app.ingestion.connectors.llm_page import LlmPageConnector
from app.ingestion.connectors.runsignup import RunSignupConnector
from app.ingestion.connectors.sample import SampleFixtureConnector
from app.ingestion.connectors.ticketmaster import TicketmasterConnector
from app.ingestion.connectors.wikidata import WikidataConnector
from app.ingestion.connectors.world_triathlon import WorldTriathlonConnector

REGISTRY = {
    SampleFixtureConnector.key: SampleFixtureConnector,
    JsonLdConnector.key: JsonLdConnector,
    ICalConnector.key: ICalConnector,
    LlmPageConnector.key: LlmPageConnector,
    WorldTriathlonConnector.key: WorldTriathlonConnector,
    RunSignupConnector.key: RunSignupConnector,
    TicketmasterConnector.key: TicketmasterConnector,
    WikidataConnector.key: WikidataConnector,
}


def get_connector(key: str):
    try:
        return REGISTRY[key]
    except KeyError as e:
        raise ValueError(f"unknown connector '{key}'. Known: {sorted(REGISTRY)}") from e
