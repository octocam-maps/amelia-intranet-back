from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Antes de importar `src` (los flags leen os.environ al importar el módulo).
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.features.absences.infrastructure.routes import create_absences_router
from src.features.announcements.infrastructure.routes import create_announcements_router
from src.features.auth.infrastructure.routes import create_auth_router
from src.features.dashboard.infrastructure.routes import create_dashboard_router
from src.features.holidays.infrastructure.routes import create_holidays_router
from src.features.mailbox.infrastructure.routes import create_mailbox_router
from src.features.notifications.infrastructure.routes import create_notifications_router
from src.features.onboarding.infrastructure.routes import create_onboarding_router
from src.features.profile.infrastructure.routes import create_profile_router
from src.features.roles.infrastructure.routes import create_roles_router
from src.features.staff.infrastructure.routes import create_staff_router
from src.features.team.infrastructure.routes import create_team_router
from src.features.time_clock.infrastructure.routes import create_time_clock_router
from src.shared.config import get_settings
from src.shared.database import get_database_pool
from src.shared.errors.base import BaseError
from src.shared.errors.handler import (
    error_handler,
    http_exception_handler,
    validation_error_handler,
)
from src.shared.logger import get_logger
from src.shared.middleware import (
    AuthMiddleware,
    ClientIPMiddleware,
    SecurityHeadersMiddleware,
    limiter,
    setup_cors,
)

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up")

    db_pool = get_database_pool()
    try:
        await db_pool.initialize()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(
            "Database connection failed", error_type=type(e).__name__, error=str(e)
        )
        logger.warning("Server will start without database. Auth endpoints will fail.")

    logger.info("Application startup complete", routes=len(app.routes))
    yield

    logger.info("Application shutting down")
    try:
        await db_pool.close()
    except Exception as e:
        logger.error("Error closing database connection", error=str(e))


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Amelia Intranet API",
        description="Backend de la intranet de RRHH y onboarding de Amelia",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.swagger_enabled else None,
        redoc_url="/redoc" if settings.swagger_enabled else None,
        openapi_url="/openapi.json" if settings.swagger_enabled else None,
    )

    setup_cors(app)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ClientIPMiddleware)

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    async def rate_limit_exceeded_handler(request, exc: RateLimitExceeded):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=429, content={"detail": "Too many requests"})

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(BaseError, error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, error_handler)

    # AuthMiddleware DEBE registrarse antes de incluir los routers para que
    # `request.state.current_user` esté disponible en cada request.
    app.add_middleware(AuthMiddleware)

    app.include_router(create_auth_router())
    app.include_router(create_dashboard_router())
    app.include_router(create_time_clock_router())
    app.include_router(create_absences_router())
    app.include_router(create_mailbox_router())
    app.include_router(create_staff_router())
    app.include_router(create_announcements_router())
    app.include_router(create_holidays_router())
    app.include_router(create_notifications_router())
    app.include_router(create_team_router())
    app.include_router(create_onboarding_router())
    app.include_router(create_profile_router())
    app.include_router(create_roles_router())
    logger.info(
        "Routers registered",
        routers=[
            "auth",
            "dashboard",
            "time-clock",
            "absences",
            "mailbox",
            "staff",
            "announcements",
            "holidays",
            "notifications",
            "team",
            "onboarding",
            "profile",
            "roles",
        ],
    )

    @app.get("/", include_in_schema=False)
    def read_root():
        return {
            "service": "amelia-intranet-back",
            "version": "0.1.0",
            "environment": settings.environment,
        }

    @app.get("/health", include_in_schema=False)
    def health_check():
        return {"status": "healthy"}

    return app


app = create_app()
