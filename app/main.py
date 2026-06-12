from fastapi import FastAPI
from app.core.config import settings
from app.core.redis_client import check_redis_connection
from app.core.database import init_db
from app.api.payments import router as payments_router
from app.api.retry import router as retry_router
from app.api.routing import router as routing_router
from app.api.circuit_breaker import router as circuit_breaker_router
from app.api.merchants import router as merchants_router
from app.api.simulator import router as simulator_router
from app.api.dashboard import router as dashboard_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="UPI-aware payment retry orchestration engine",
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.on_event("startup")
def startup():
    init_db()


app.include_router(payments_router)
app.include_router(retry_router)
app.include_router(routing_router)
app.include_router(circuit_breaker_router)
app.include_router(merchants_router)
app.include_router(simulator_router)
app.include_router(dashboard_router)


@app.get("/")
def root():
    return {
        "service":     settings.APP_NAME,
        "version":     settings.APP_VERSION,
        "status":      "running",
        "docs":        "/docs",
        "dashboard":   "/dashboard",
        "health":      "/health",
        "info":        "/info"
    }


@app.get("/health")
def health():
    redis_ok = check_redis_connection()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis":  "connected" if redis_ok else "disconnected"
    }


@app.get("/info")
def info():
    """
    Full system capabilities and endpoint reference.
    """
    return {
        "service":     settings.APP_NAME,
        "version":     settings.APP_VERSION,
        "description": "UPI-aware payment retry orchestration engine",

        "capabilities": [
            "NPCI UPI error code classification (U69, Z9, U30, U44, U16, U99)",
            "Exponential backoff with full jitter (AWS-recommended algorithm)",
            "Three-state circuit breaker per gateway (CLOSED/OPEN/HALF_OPEN)",
            "Intelligent gateway routing with 5-minute success rate tracking",
            "Merchant SLA awareness (Zomato 8s, Swiggy 12s, Amazon 30s)",
            "Redis Streams event queue with consumer group delivery",
            "Full per-payment retry timeline audit trail",
            "Peak hour failure spike detection and auto-throttling",
            "Dual storage: Redis hot path + PostgreSQL permanent audit log",
            "Async PostgreSQL writes via Celery (non-blocking hot path)",
        ],

        "tech_stack": {
            "api":             "FastAPI + Pydantic",
            "event_queue":     "Redis Streams",
            "cache":           "Redis",
            "database":        "PostgreSQL + SQLAlchemy",
            "async_tasks":     "Celery + Redis broker",
            "containerization": "Docker + Docker Compose",
            "load_testing":    "Locust"
        },

        "benchmarks": {
            "rps":           "80 RPS sustained",
            "median_latency": "9ms",
            "p99_latency":   "130ms",
            "concurrent_users": 100,
            "failure_rate":  "0%",
            "test_requests": "5700+"
        },

        "endpoints": {
            "payments": [
                "POST /payments/fail — Report failed payment",
                "GET  /payments/{id} — Get payment by ID",
                "GET  /payments/{id}/timeline — Full retry audit trail",
                "GET  /payments/history/all — PostgreSQL history",
                "GET  /payments/stream/events — Stream queue contents"
            ],
            "retry": [
                "GET /retry/plan/{id} — Full retry schedule",
                "GET /retry/simulate/{error_class} — Backoff simulation"
            ],
            "routing": [
                "GET  /routing/status — Live gateway health",
                "GET  /routing/best — Best available gateway",
                "POST /routing/simulate/failure/{bank}",
                "POST /routing/simulate/success/{bank}"
            ],
            "circuit_breaker": [
                "GET  /circuit-breaker/status — All circuit states",
                "GET  /circuit-breaker/status/{bank}",
                "GET  /circuit-breaker/can-pass/{bank}",
                "POST /circuit-breaker/simulate/failure/{bank}",
                "POST /circuit-breaker/simulate/success/{bank}"
            ],
            "merchants": [
                "GET /merchants/sla — All merchant SLA configs",
                "GET /merchants/priority-score/{id}",
                "GET /merchants/breaches"
            ],
            "simulator": [
                "GET  /simulator/status — System status",
                "POST /simulator/spike — Trigger failure spike",
                "POST /simulator/burst/{count} — Send N payments",
                "GET  /simulator/error-distribution"
            ],
            "system": [
                "GET /health — Health check",
                "GET /info — This endpoint",
                "GET /dashboard — Live admin dashboard",
                "GET /docs — Swagger UI"
            ]
        },

        "github": "https://github.com/UnmeshaSingh/upi-retry-engine"
    }