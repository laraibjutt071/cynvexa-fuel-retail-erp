import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    attendance,
    audit,
    auth,
    credit_collections,
    credit_customers,
    dispensers,
    expense_categories,
    expenses,
    fuel_grades,
    fuel_prices,
    health,
    invitations,
    inventory_items,
    inventory_movements,
    meter_events,
    nozzle_overview,
    nozzles,
    org_reports,
    organizations,
    payment_methods,
    platform,
    reading_corrections,
    reports,
    roles,
    shift_cash_movements,
    shift_reconciliation,
    shift_templates,
    shift_tenders,
    shifts,
    stations,
    subscriptions,
    support_sessions,
    supplier_ledger,
    suppliers,
    tanker_receipts,
    tanks,
    users,
)
from app.config import get_settings
from app.core.logging_config import configure_logging
from app.exceptions import AppError

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("cynvexa")
access_logger = logging.getLogger("cynvexa.access")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CYNVEXA Fuel Retail ERP API",
        version="0.1.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        access_logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else None,
            },
        )
        response.headers["X-Request-ID"] = request_id
        # Two headers safe to set unconditionally at the application layer -
        # neither can break a working frontend (unlike a strict
        # Content-Security-Policy, which risks blocking Next.js's own
        # scripts/styles if set without testing against the real build).
        # HSTS, CSP and frame-ancestors are deliberately NOT set here: they
        # belong at the reverse-proxy layer once one is actually deployed in
        # front of HTTPS (see docs/CLOUD_DEPLOYMENT_PLAN.md) - setting HSTS
        # on a server that might still be reached over plain HTTP in some
        # environment would be actively wrong, not just incomplete.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        # Routine 4xx AppErrors (not found / conflict / permission denied) are
        # expected traffic and already show up in the access log's status
        # code - logging every one would just be noise. But an AppError
        # raised `from` an underlying exception (e.g. /ready wrapping a
        # real DB connection failure) carries real diagnostic value that
        # would otherwise be silently dropped, so that case is logged.
        if exc.__cause__ is not None:
            logger.error(
                "%s %s failed: %s",
                request.method,
                request.url.path,
                exc.detail,
                exc_info=exc.__cause__,
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak tracebacks, SQL text or secrets to the client. Full detail goes
        # to the server log only.
        logger.exception("Unhandled exception while processing %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(organizations.router)
    app.include_router(stations.router)
    app.include_router(users.router)
    app.include_router(roles.router)
    app.include_router(audit.router)
    app.include_router(fuel_grades.router)
    # balances_router (literal "/suppliers/balances") must be registered
    # before suppliers.router ("/suppliers/{supplier_id}") - FastAPI
    # matches routes in registration order across the whole app, and a
    # parametrized path registered first would otherwise swallow the
    # literal one (caught live: GET /suppliers/balances was being parsed
    # as supplier_id="balances" and 422ing).
    app.include_router(supplier_ledger.balances_router)
    app.include_router(suppliers.router)
    app.include_router(tanks.router)
    app.include_router(dispensers.router)
    app.include_router(nozzles.router)
    app.include_router(nozzle_overview.router)
    app.include_router(fuel_prices.router)
    app.include_router(tanker_receipts.router)
    app.include_router(shifts.router)
    app.include_router(reading_corrections.router)
    app.include_router(meter_events.router)
    app.include_router(payment_methods.router)
    app.include_router(credit_collections.balances_router)
    app.include_router(credit_customers.router)
    app.include_router(shift_tenders.router)
    app.include_router(shift_cash_movements.router)
    app.include_router(shift_reconciliation.router)
    app.include_router(supplier_ledger.router)
    app.include_router(credit_collections.router)
    app.include_router(expenses.router)
    app.include_router(inventory_items.router)
    app.include_router(inventory_movements.router)
    app.include_router(reports.router)
    app.include_router(reports.org_router)
    app.include_router(reports.supplier_report_router)
    app.include_router(org_reports.router)
    app.include_router(expense_categories.router)
    app.include_router(shift_templates.router)
    app.include_router(attendance.attendance_router)
    app.include_router(attendance.payroll_router)
    app.include_router(platform.router)
    app.include_router(platform.public_router)
    app.include_router(invitations.router)
    app.include_router(invitations.public_router)
    app.include_router(support_sessions.router)
    app.include_router(subscriptions.router)

    return app


app = create_app()
