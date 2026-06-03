from fastapi import APIRouter, HTTPException
from app.services.routing_service import (
    record_attempt,
    record_failure,
    record_success,
    get_best_gateway,
    get_all_gateway_status,
    get_gateway_stats,
    GATEWAY_REGISTRY,
    FAILURE_THRESHOLD,
    WINDOW_SECONDS
)

router = APIRouter(prefix="/routing", tags=["Routing"])


@router.get("/status")
def gateway_status():
    """
    Live health status of all payment gateways.
    Shows attempts, failures, success rate, and block status.
    """
    return {
        "failure_threshold":   FAILURE_THRESHOLD,
        "window_seconds":      WINDOW_SECONDS,
        "window_minutes":      WINDOW_SECONDS // 60,
        "gateways":            get_all_gateway_status()
    }


@router.get("/best")
def best_gateway(exclude: str = None):
    """
    Returns the best available gateway.
    Use exclude= to simulate a failed gateway being skipped.
    """
    gateway = get_best_gateway(exclude_bank=exclude)

    if not gateway:
        raise HTTPException(
            status_code=503,
            detail="No gateways available — all blocked"
        )

    return {
        "recommended_gateway": gateway,
        "gateway_name":        GATEWAY_REGISTRY[gateway]["name"],
        "excluded":            exclude,
        "reason":              "Highest priority unblocked gateway"
    }


@router.post("/simulate/attempt/{bank}")
def simulate_attempt(bank: str):
    """Simulate a payment attempt through a gateway."""
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )
    record_attempt(bank)
    return {
        "recorded": "attempt",
        "bank": bank,
        "stats": get_gateway_stats(bank)
    }


@router.post("/simulate/failure/{bank}")
def simulate_failure(bank: str):
    """
    Simulate a payment failure through a gateway.
    After 3 failures, gateway gets blocked automatically.
    """
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )
    record_attempt(bank)
    record_failure(bank)
    return {
        "recorded": "failure",
        "bank": bank,
        "stats": get_gateway_stats(bank)
    }


@router.post("/simulate/success/{bank}")
def simulate_success(bank: str):
    """
    Simulate a successful payment.
    Clears any block on the gateway.
    """
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )
    record_attempt(bank)
    record_success(bank)
    return {
        "recorded": "success",
        "bank": bank,
        "stats": get_gateway_stats(bank)
    }