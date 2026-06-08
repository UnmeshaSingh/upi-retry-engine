import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.db_models import PaymentRecord, RetryAttempt, SLABreachRecord, PaymentStatusDB
from app.models.payment import FailedPaymentEvent, UPI_ERROR_CLASS_MAP

log = logging.getLogger(__name__)


def save_payment_to_db(event: FailedPaymentEvent, db: Session) -> PaymentRecord:
    """Save a failed payment to PostgreSQL."""
    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    record = PaymentRecord(
        id=event.payment_id,
        amount=event.amount,
        upi_error_code=event.upi_error_code.value,
        error_class=error_class.value,
        remitter_bank=event.remitter_bank,
        beneficiary_bank=event.beneficiary_bank,
        merchant_id=event.merchant_id,
        merchant_name=event.merchant_name,
        upi_id=event.upi_id,
        status=PaymentStatusDB.FAILED,
        retry_count=0,
        failed_at=event.failed_at
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    log.info(f"DB: Payment saved — {record.id[:8]} ({record.merchant_name})")
    return record


def save_retry_attempt(
    payment_id: str,
    attempt_number: int,
    gateway: str,
    circuit_state: str,
    delay_seconds: float,
    db: Session
) -> RetryAttempt:
    """Save a retry attempt to PostgreSQL."""
    attempt = RetryAttempt(
        payment_id=payment_id,
        attempt_number=attempt_number,
        gateway=gateway,
        circuit_state=circuit_state,
        delay_seconds=delay_seconds,
        status="SCHEDULED"
    )

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    log.info(f"DB: Retry attempt #{attempt_number} saved for {payment_id[:8]}")
    return attempt


def save_sla_breach(
    payment_id: str,
    merchant_id: str,
    merchant_name: str,
    sla_seconds: int,
    elapsed_seconds: float,
    db: Session
) -> SLABreachRecord:
    """Save an SLA breach to PostgreSQL."""
    breach = SLABreachRecord(
        payment_id=payment_id,
        merchant_id=merchant_id,
        merchant_name=merchant_name,
        sla_seconds=sla_seconds,
        elapsed_seconds=elapsed_seconds
    )

    db.add(breach)
    db.commit()
    db.refresh(breach)

    log.warning(f"DB: SLA breach saved — {merchant_name} ({elapsed_seconds}s)")
    return breach


def get_payment_history(
    db: Session,
    limit: int = 20,
    status: str = None,
    merchant_id: str = None
) -> list:
    """Query payment history from PostgreSQL."""
    query = db.query(PaymentRecord)

    if status:
        query = query.filter(PaymentRecord.status == status)

    if merchant_id:
        query = query.filter(PaymentRecord.merchant_id == merchant_id)

    query = query.order_by(PaymentRecord.failed_at.desc()).limit(limit)
    return query.all()


def get_payment_with_retries(payment_id: str, db: Session):
    """Get a payment with all its retry attempts."""
    payment = db.query(PaymentRecord).filter(
        PaymentRecord.id == payment_id
    ).first()

    if not payment:
        return None, []

    attempts = db.query(RetryAttempt).filter(
        RetryAttempt.payment_id == payment_id
    ).order_by(RetryAttempt.attempt_number).all()

    return payment, attempts