"""
FastAPI application factory for SVANT.
Configures middleware, routers, exception handlers, and serves the web UI.
"""

from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from svant import __version__, __app_name__
from svant.api.routes import health, projects, files, search, stats, indexing
from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.api")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings.ensure_directories()

    app = FastAPI(
        title=__app_name__,
        version=__version__,
        description="Local-First Project and File Intelligence Engine",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS configuration for local development / desktop webview
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "InternalServerError", "detail": "An unexpected error occurred. Check local logs for details."},
        )

    # Include API Routers
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(files.router)
    app.include_router(indexing.router)
    app.include_router(search.router)
    app.include_router(stats.router)

    # Mount Web Static Assets
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.is_dir():
        # Serve static assets (css, js, assets)
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        # Root route serving index.html
        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            index_path = web_dir / "index.html"
            return FileResponse(str(index_path))

    return app


# Application entry point instance for uvicorn
app = create_app()
