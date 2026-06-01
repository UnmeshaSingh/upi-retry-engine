from fastapi import APIRouter, HTTPException
from app.models.payment import (
    FailedPaymentEvent,
    PaymentEventResponse,
    UPI_ERROR_CLASS_MAP
)

router = APIRouter(prefix="/payments", tags=["Payments"])

# In-memory store for now — Day 11 we move to PostgreSQL
payment_store: dict = {}


@router.post("/fail", response_model=PaymentEventResponse, status_code=201)
def report_failed_payment(event: FailedPaymentEvent):
    """
    Accepts a failed UPI payment event.
    Classifies the error and stores it for retry orchestration.
    """
    # Classify the error
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    # Store it
    payment_store[event.payment_id] = event

    return PaymentEventResponse(
        payment_id=event.payment_id,
        status=event.status,
        upi_error_code=event.upi_error_code,
        error_class=error_class,
        amount=event.amount,
        merchant_name=event.merchant_name,
        retry_count=event.retry_count,
        failed_at=event.failed_at,
        message=f"Payment failure recorded. Error class: {error_class.value}. Retry orchestration pending."
    )


@router.get("/{payment_id}", response_model=PaymentEventResponse)
def get_payment(payment_id: str):
    """
    Retrieve a stored payment event by ID.
    """
    event = payment_store.get(payment_id)

    if not event:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")

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
        message=f"Payment found. Error class: {error_class.value}."
    )