from fastapi import APIRouter, HTTPException
from app.services.circuit_breaker import (
    get_circuit_status,
    get_all_circuit_status,
    record_success,
    record_failure,
    can_pass_request,
    CircuitState,
    FAILURE_THRESHOLD,
    RECOVERY_TIMEOUT,
    SUCCESS_THRESHOLD
)
from app.services.routing_service import GATEWAY_REGISTRY

router = APIRouter(prefix="/circuit-breaker", tags=["Circuit Breaker"])


@router.get("/status")
def all_circuit_status():
    """
    Live circuit breaker state for all gateways.
    Shows CLOSED / OPEN / HALF_OPEN per bank.
    """
    return {
        "config": {
            "failure_threshold":  FAILURE_THRESHOLD,
            "recovery_timeout_s": RECOVERY_TIMEOUT,
            "success_threshold":  SUCCESS_THRESHOLD,
        },
        "circuits": get_all_circuit_status()
    }


@router.get("/status/{bank}")
def circuit_status(bank: str):
    """Get circuit breaker status for a specific gateway."""
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )
    return get_circuit_status(bank)


@router.post("/simulate/failure/{bank}")
def simulate_failure(bank: str):
    """
    Simulate a gateway failure.
    After 5 failures circuit trips to OPEN.
    """
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )

    record_failure(bank)
    status = get_circuit_status(bank)

    return {
        "action":  "failure_recorded",
        "bank":    bank,
        "circuit": status
    }


@router.post("/simulate/success/{bank}")
def simulate_success(bank: str):
    """
    Simulate a gateway success.
    In HALF_OPEN: accumulates toward closing circuit.
    """
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )

    record_success(bank)
    status = get_circuit_status(bank)

    return {
        "action":  "success_recorded",
        "bank":    bank,
        "circuit": status
    }


@router.get("/can-pass/{bank}")
def check_can_pass(bank: str):
    """
    Check if a request can be sent to this gateway right now.
    Use this before routing a retry attempt.
    """
    bank = bank.upper()
    if bank not in GATEWAY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank. Valid: {list(GATEWAY_REGISTRY.keys())}"
        )

    allowed = can_pass_request(bank)
    status  = get_circuit_status(bank)

    return {
        "bank":        bank,
        "can_pass":    allowed,
        "state":       status["state"],
        "reason":      "Circuit closed or half-open" if allowed else f"Circuit OPEN — retry in {status['time_until_half_open']}"
    }