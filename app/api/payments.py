import json
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models.payment import (
    FailedPaymentEvent,
    PaymentEventResponse,
    UPI_ERROR_CLASS_MAP
)
from app.core.redis_client import get_redis
from app.core.database import get_db
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
from app.services.db_service import (
    save_payment_to_db,
    get_payment_history,
    get_payment_with_retries
)

router = APIRouter(prefix="/payments", tags=["Payments"])

PAYMENT_KEY_PREFIX = "payment"
PAYMENT_TTL_SECONDS = 86400  # 24 hours


@router.post("/fail", response_model=PaymentEventResponse, status_code=201)
def report_failed_payment(
    event: FailedPaymentEvent,
    redis=Depends(get_redis),
    db: Session = Depends(get_db)
):
    """
    Accepts a failed UPI payment event.
    Hot path:   Redis store + Stream push (sub-millisecond)
    Async path: PostgreSQL write via Celery (non-blocking)
    """
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    # ── HOT PATH (synchronous, must be fast) ──────────────────────
    # 1. Store in Redis
    redis_key = f"{PAYMENT_KEY_PREFIX}:{event.payment_id}"
    redis.setex(redis_key, PAYMENT_TTL_SECONDS, event.model_dump_json())

    # 2. Push to stream
    stream_entry_id = push_to_stream(event)

    # ── ASYNC PATH (non-blocking, PostgreSQL) ─────────────────────
    # 3. Enqueue DB write as Celery task
    try:
        from app.tasks.db_tasks import save_payment_async
        save_payment_async.delay({
            "payment_id":       event.payment_id,
            "amount":           event.amount,
            "upi_error_code":   event.upi_error_code.value,
            "error_class":      error_class.value,
            "remitter_bank":    event.remitter_bank,
            "beneficiary_bank": event.beneficiary_bank,
            "merchant_id":      event.merchant_id,
            "merchant_name":    event.merchant_name,
            "upi_id":           event.upi_id,
            "failed_at":        event.failed_at.isoformat()
        })
        db_write = "async"
    except Exception:
        # Celery unavailable — fall back to sync write
        save_payment_to_db(event, db)
        db_write = "sync_fallback"

    return PaymentEventResponse(
        payment_id=event.payment_id,
        status=event.status,
        upi_error_code=event.upi_error_code,
        error_class=error_class,
        amount=event.amount,
        merchant_name=event.merchant_name,
        retry_count=event.retry_count,
        failed_at=event.failed_at,
        message=f"Payment queued (stream: {stream_entry_id}, db_write: {db_write}). Error: {error_class.value}."
    )


@router.get("/history/all")
def get_history(
    limit: int = 20,
    status: str = None,
    merchant_id: str = None,
    db: Session = Depends(get_db)
):
    """
    Query payment history from PostgreSQL.
    Supports filtering by status and merchant.
    """
    payments = get_payment_history(
        db,
        limit=limit,
        status=status,
        merchant_id=merchant_id
    )

    return {
        "total": len(payments),
        "payments": [
            {
                "payment_id":     p.id,
                "merchant_name":  p.merchant_name,
                "amount":         p.amount,
                "upi_error_code": p.upi_error_code,
                "error_class":    p.error_class,
                "status":         p.status,
                "retry_count":    p.retry_count,
                "failed_at":      p.failed_at.isoformat(),
            }
            for p in payments
        ]
    }


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

    timeline = get_timeline(payment_id)

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