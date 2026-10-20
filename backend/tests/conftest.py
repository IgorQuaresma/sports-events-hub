"""Test setup: a dedicated Postgres database (DATABASE_URL_TEST) migrated once per session."""

import os
from collections.abc import AsyncIterator

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from alembic import command

TEST_URL = os.environ.get(
    "DATABASE_URL_TEST", "postgresql+asyncpg://postgres:postgres@localhost:5432/hub_test"
)
os.environ["DATABASE_URL"] = TEST_URL
os.environ["RAW_DIR"] = "/tmp/hub-test-raw"
os.environ["ANTHROPIC_API_KEY"] = ""


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session", autouse=True)
async def seeded(migrated_db):
    from app.cli import _seed_taxonomy
    from app.core.db import dispose_engine

    await _seed_taxonomy()
    yield
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
