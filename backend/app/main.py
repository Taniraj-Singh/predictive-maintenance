import asyncio
from datetime import datetime
from pathlib import Path
from loguru import logger

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.routers import (
    ai,
    alarms,
    attachments,
    audit,
    dashboard,
    health,
    history,
    jobs,
    knowledge,
    machines,
    metrics,
    mqtt,
    notifications,
    opcua,
    predictions,
    realtime,
    reports,
    roles,
    sensor_data,
    sensors,
    settings as settings_router,
    simulator,
    tickets,
    users,
    webhooks,
)
from app.core.config import get_settings, validate_production_secrets
from app.mqtt.consumer import mqtt_ingestor
from app.opcua.connector import opcua_connector
from app.services import notification_service

settings = get_settings()

# Fail fast if running in a production-like environment with insecure defaults.
validate_production_secrets(settings)

app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    debug=settings.debug,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Custom OpenAPI schema to ensure proper version field
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=settings.project_name,
        version="1.0.0",
        description="Predictive Maintenance Platform API - Complete API for managing machines, sensors, predictions, alarms, and more.",
        routes=app.routes,
    )
    # Explicitly set OpenAPI version to 3.1.0
    openapi_schema["openapi"] = "3.1.0"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Performance optimizations
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

# Custom exception handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Provide helpful 404 messages with available endpoints"""
    return JSONResponse(
        status_code=404,
        content={
            "detail": f"Endpoint not found: {request.url.path}",
            "message": "The requested endpoint does not exist. Here are some available endpoints:",
            "available_endpoints": {
                "root": "/",
                "health": "/health",
                "status": "/status",
                "api_docs": "/docs",
                "openapi": "/openapi.json",
                "dashboard": "/dashboard/overview",
                "ai_status": "/ai/status",
                "mqtt_status": "/mqtt/status",
                "machines": "/machines",
                "sensors": "/sensors",
                "predictions": "/predictions",
                "alarms": "/alarms",
                "tickets": "/tickets",
                "reports": "/reports/generate"
            },
            "tip": "Visit /docs for the complete API documentation"
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Provide helpful validation error messages"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "message": "The request data is invalid. Please check your input.",
            "errors": exc.errors(),
            "path": str(request.url.path)
        }
    )

reports_dir = settings.reports_dir
reports_dir.mkdir(parents=True, exist_ok=True)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(machines.router)
app.include_router(sensors.router)
app.include_router(sensor_data.router)
app.include_router(predictions.router)
app.include_router(alarms.router)
app.include_router(tickets.router)
app.include_router(reports.router)  # Must be before static mount to handle /reports/download routes
app.include_router(notifications.router)
app.include_router(knowledge.router)
app.include_router(history.router)
app.include_router(dashboard.router)
app.include_router(ai.router)
app.include_router(mqtt.router)
app.include_router(opcua.router)
app.include_router(settings_router.router)
app.include_router(webhooks.router)
app.include_router(audit.router)
app.include_router(realtime.router)
app.include_router(attachments.router)
app.include_router(metrics.router)
app.include_router(jobs.router)
app.include_router(simulator.router)

# Mount static files AFTER routers so router routes take precedence
app.mount("/reports", StaticFiles(directory=reports_dir), name="reports")


@app.get("/")
async def root():
    """Root endpoint - shows system information and available endpoints"""
    return {
        "service": "Predictive Maintenance Platform",
        "version": "1.0.0",
        "status": "running",
        "message": "✅ Backend API is running successfully",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "api_docs": "/docs",
            "openapi": "/openapi.json",
            "dashboard": "/dashboard/overview",
            "ai_status": "/ai/status",
            "mqtt_status": "/mqtt/status"
        },
        "services": {
            "backend": "✅ Running",
            "database": "Check /health/ready",
            "ai_service": "Check /ai/status",
            "mqtt": "Check /mqtt/status"
        }
    }


@app.on_event("startup")
async def startup_event():
    # Get the current event loop for async operations
    loop = asyncio.get_event_loop()
    mqtt_ingestor.start(loop)
    # Restore persisted OPC UA sources before starting the connector worker so
    # mappings survive backend restarts (restart recovery).
    try:
        from app.opcua.repository import load_active_sources_into_registry
        await load_active_sources_into_registry()
    except Exception as e:
        logger.warning(f"OPC UA source restore skipped: {e}")
    # Start OPC UA connector worker (no‑op if no active sources yet)
    opcua_connector.start(loop)
    # Give MQTT consumer a moment to start
    await asyncio.sleep(1)
    logger.info("✅ Startup complete - MQTT consumer should be running")
    
    # Start live data generator as fallback (runs every 5 seconds)
    # This ensures live data is always available even if MQTT isn't working
    from app.tasks.live_data_generator import start_live_data_generator
    loop.create_task(start_live_data_generator(interval_seconds=5))
    logger.info("🚀 Live data generator started (5s interval)")

    # Start offline-sensor detection monitor
    from app.tasks.offline_monitor import start_offline_monitor
    loop.create_task(start_offline_monitor())

    # Ensure demo users (admin/engineer/viewer) exist so first login always works
    try:
        from app.tasks.seed_demo_data import seed_demo_users, seed_sample_machines

        logger.info("👤 Ensuring demo users exist (admin/engineer/viewer)")
        await seed_demo_users()
        logger.info("✅ Demo users verified/created")
        
        logger.info("🏭 Ensuring demo machines exist (Pump-01, Motor-02, Compressor-A, Conveyor-B2)")
        await seed_sample_machines()
        logger.info("✅ Demo machines verified/created")
    except Exception as e:
        # Don't block startup if seeding fails (e.g., schema differences)
        logger.error(f"Failed to ensure demo data: {e}")
    
    # Verify email configuration if available (non-blocking best-effort check)
    verify_email = getattr(notification_service, "verify_email_transport", None)
    if verify_email:
        await verify_email()


@app.on_event("shutdown")
async def shutdown_event():
    mqtt_ingestor.stop()
    await opcua_connector.stop()

