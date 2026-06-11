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

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="UPI-aware payment retry orchestration engine"
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

@app.get("/")
def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }

@app.get("/health")
def health():
    redis_ok = check_redis_connection()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected"
    }