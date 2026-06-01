import json
from fastapi import APIRouter, HTTPException, Depends
from app.models.payment import (
    FailedPaymentEvent,
    PaymentEventResponse,
    UPI_ERROR_CLASS_MAP
)
from app.core.redis_client import get_redis

router = APIRouter(prefix="/payments", tags=["Payments"])

# Redis key pattern: payment:{payment_id}
PAYMENT_KEY_PREFIX = "payment"
PAYMENT_TTL_SECONDS = 86400  # 24 hours


@router.post("/fail", response_model=PaymentEventResponse, status_code=201)
def report_failed_payment(
    event: FailedPaymentEvent,
    redis=Depends(get_redis)
):
    """
    Accepts a failed UPI payment event.
    Classifies the error and stores it in Redis.
    """
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    # Store in Redis as JSON with 24hr TTL
    redis_key = f"{PAYMENT_KEY_PREFIX}:{event.payment_id}"
    redis.setex(
        redis_key,
        PAYMENT_TTL_SECONDS,
        event.model_dump_json()
    )

    return PaymentEventResponse(
        payment_id=event.payment_id,
        status=event.status,
        upi_error_code=event.upi_error_code,
        error_class=error_class,
        amount=event.amount,
        merchant_name=event.merchant_name,
        retry_count=event.retry_count,
        failed_at=event.failed_at,
        message=f"Payment stored in Redis. Error class: {error_class.value}. Retry orchestration pending."
    )


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