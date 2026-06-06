import json
from fastapi import APIRouter, HTTPException, Depends
from app.models.payment import (
    FailedPaymentEvent,
    PaymentEventResponse,
    UPI_ERROR_CLASS_MAP
)
from app.core.redis_client import get_redis
from app.services.stream_service import (
    push_to_stream,
    read_stream_events,
    get_stream_length
)
from app.services.timeline_service import (
    get_timeline,
    record_payment_failed,
    record_retry_scheduled,
    record_abandoned
)

router = APIRouter(prefix="/payments", tags=["Payments"])

PAYMENT_KEY_PREFIX = "payment"
PAYMENT_TTL_SECONDS = 86400  # 24 hours


@router.post("/fail", response_model=PaymentEventResponse, status_code=201)
def report_failed_payment(
    event: FailedPaymentEvent,
    redis=Depends(get_redis)
):
    """
    Accepts a failed UPI payment event.
    1. Stores it in Redis with TTL
    2. Pushes it into Redis Stream for retry processing
    """
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    # Store payment in Redis
    redis_key = f"{PAYMENT_KEY_PREFIX}:{event.payment_id}"
    redis.setex(
        redis_key,
        PAYMENT_TTL_SECONDS,
        event.model_dump_json()
    )

    # Push to stream
    stream_entry_id = push_to_stream(event)

    return PaymentEventResponse(
        payment_id=event.payment_id,
        status=event.status,
        upi_error_code=event.upi_error_code,
        error_class=error_class,
        amount=event.amount,
        merchant_name=event.merchant_name,
        retry_count=event.retry_count,
        failed_at=event.failed_at,
        message=f"Payment stored and queued in stream (entry: {stream_entry_id}). Error class: {error_class.value}."
    )


@router.get("/stream/events")
def get_stream_events(count: int = 10):
    """
    Read recent events from the payments stream.
    Shows what the retry worker will process.
    """
    events = read_stream_events(count=count)
    stream_len = get_stream_length()

    return {
        "total_events_in_stream": stream_len,
        "fetched": len(events),
        "events": events
    }


@router.get("/{payment_id}/timeline")
def get_payment_timeline(
    payment_id: str,
    redis=Depends(get_redis)
):
    """
    Get the full retry timeline for a payment.
    Shows every event: failure, retry scheduled, gateway switch, etc.
    """
    # Verify payment exists
    payment_key = f"{PAYMENT_KEY_PREFIX}:{payment_id}"
    data = redis.get(payment_key)

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Payment {payment_id} not found"
        )

    event_dict = json.loads(data)
    event = FailedPaymentEvent(**event_dict)
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    # Get timeline
    timeline = get_timeline(payment_id)

    # Get retry plan from Redis
    retry_key = f"retry_plan:{payment_id}"
    retry_plan = redis.hgetall(retry_key)

    return {
        "payment_id":     payment_id,
        "merchant_name":  event.merchant_name,
        "amount":         event.amount,
        "upi_error_code": event.upi_error_code.value,
        "error_class":    error_class.value,
        "current_status": event.status.value,
        "retry_count":    event.retry_count,
        "timeline":       timeline,
        "retry_plan":     retry_plan if retry_plan else None,
        "total_events":   len(timeline)
    }


@router.get("/{payment_id}", response_model=PaymentEventResponse)
def get_payment(
    payment_id: str,
    redis=Depends(get_redis)
):
    """
    Retrieve a payment event from Redis by ID.
    """
    redis_key = f"{PAYMENT_KEY_PREFIX}:{payment_id}"
    data = redis.get(redis_key)

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Payment {payment_id} not found"
        )

    event_dict = json.loads(data)
    event = FailedPaymentEvent(**event_dict)
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    return PaymentEventResponse(
        payment_id=event.payment_id,
        status=event.status,
        upi_error_code=event.upi_error_code,
        error_class=error_class,
        amount=event.amount,
        merchant_name=event.merchant_name,
        retry_count=event.retry_count,
        failed_at=event.failed_at,
        message=f"Payment retrieved from Redis. Error class: {error_class.value}."
    )