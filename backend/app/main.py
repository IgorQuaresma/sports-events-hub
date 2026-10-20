import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, events, search, sources, taxonomy, weather
from app.core.config import get_settings
from app.core.db import dispose_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# JSON API: nothing may be framed, scripted or loaded from these responses.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
# Swagger UI loads its assets from jsDelivr.
DOCS_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: "
    "https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        openapi_url="/v1/openapi.json",
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        is_docs = request.url.path in ("/docs", "/docs/oauth2-redirect")
        h = response.headers  # setdefault: endpoints may set stricter values themselves
        h.setdefault("Content-Security-Policy", DOCS_CSP if is_docs else API_CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if settings.is_prod:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    app.include_router(search.router, prefix="/v1")
    app.include_router(events.router, prefix="/v1")
    app.include_router(weather.router, prefix="/v1")
    app.include_router(taxonomy.router, prefix="/v1")
    app.include_router(sources.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
