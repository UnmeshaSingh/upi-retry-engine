import json
from fastapi import APIRouter, HTTPException, Depends
from app.core.redis_client import get_redis
from app.models.payment import FailedPaymentEvent, UPI_ERROR_CLASS_MAP
from app.services.retry_scheduler import (
    build_full_retry_schedule,
    get_retry_delay,
    should_retry,
    get_max_retries,
    RETRY_CONFIG
)

router = APIRouter(prefix="/retry", tags=["Retry"])


@router.get("/plan/{payment_id}")
def get_retry_plan(payment_id: str, redis=Depends(get_redis)):
    """
    Get the full retry schedule for a payment.
    Shows every planned attempt with exact delay and timestamp.
    """
    # Fetch payment from Redis
    payment_key = f"payment:{payment_id}"
    data = redis.get(payment_key)

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Payment {payment_id} not found"
        )

    event_dict = json.loads(data)
    event = FailedPaymentEvent(**event_dict)
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    # Build full retry schedule
    schedule = build_full_retry_schedule(error_class.value)

    return {
        "payment_id":    payment_id,
        "merchant_name": event.merchant_name,
        "amount":        event.amount,
        "upi_error_code": event.upi_error_code.value,
        "error_class":   error_class.value,
        "max_retries":   get_max_retries(error_class.value),
        "will_retry":    len(schedule) > 0,
        "retry_schedule": schedule,
        "note": "Delays include full jitter — each call returns different values"
    }


@router.get("/simulate/{error_class}")
def simulate_backoff(error_class: str, attempts: int = 5):
    """
    Simulate what the backoff schedule looks like for any error class.
    Run this multiple times to see jitter in action.
    """
    error_class = error_class.upper()

    if error_class not in RETRY_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown error class. Valid: {list(RETRY_CONFIG.keys())}"
        )

    config = RETRY_CONFIG[error_class]
    results = []

    for attempt in range(min(attempts, config["max_retries"] or attempts)):
        delay = get_retry_delay(error_class, attempt)
        if delay is None:
            break
        results.append({
            "attempt":       attempt + 1,
            "delay_seconds": delay,
        })

    return {
        "error_class": error_class,
        "strategy":    config["strategy"],
        "base_delay":  config["base_delay"],
        "max_delay":   config["max_delay"],
        "simulated_delays": results,
        "note": "Call again to see different jitter values"
    }