from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.exceptions import QuotaExceededError, ScheduleNotFoundError
from app.settings import AppSettings, get_settings
from app.startup import on_shutdown, on_startup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await on_startup(app)
    yield
    await on_shutdown(app)


def create_app(settings: AppSettings) -> FastAPI:
    app = FastAPI(
        title="Contelligence Agent",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.routers import admin, agent, health
    from app.routers import agents as agents_router
    from app.routers import dashboard, events, schedules, skills, webhooks

    prefix = f"/api/{settings.API_VERSION}"
    
    app.include_router(agent.router, prefix=prefix)
    app.include_router(agents_router.router, prefix=prefix)
    app.include_router(health.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    # Scheduling Engine routers
    app.include_router(schedules.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)
    app.include_router(webhooks.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(skills.router, prefix=prefix)

    # QuotaExceededError → 429
    @app.exception_handler(QuotaExceededError)
    async def quota_exceeded_handler(
        request: Request, exc: QuotaExceededError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "detail": str(exc),
                "session_id": exc.session_id,
                "resource": exc.resource,
            },
        )

    # ScheduleNotFoundError → 404
    @app.exception_handler(ScheduleNotFoundError)
    async def schedule_not_found_handler(
        request: Request, exc: ScheduleNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": str(exc),
                "schedule_id": exc.schedule_id,
            },
        )

    return app

settings: AppSettings = get_settings()
    
# Module-level app instance for `uvicorn src.main:app`
app = create_app(settings)

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen binary — pass app object directly
        # (import string "main:app" doesn't work when code is frozen)
        uvicorn.run(app,
                    host=settings.API_HOST,
                    port=settings.API_PORT,
                    workers=1,
                    use_colors=True,
                    log_config=None,
                    log_level="debug" if settings.LOG_LEVEL == "DEBUG" else "info",
        )
    else:
        uvicorn.run("main:app", 
                    reload=settings.LOG_LEVEL == "DEBUG",
                    host=settings.API_HOST,
                    port=settings.API_PORT,
                    workers=1,
                    use_colors=True,
                    log_config=None,
                    log_level="debug" if settings.LOG_LEVEL == "DEBUG" else "info",
        )