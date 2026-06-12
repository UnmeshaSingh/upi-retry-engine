import logging
from app.core.celery_app import celery_app
from app.core.database import SessionLocal

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="app.tasks.db_tasks.save_payment_async"
)
def save_payment_async(self, payment_data: dict):
    """
    Async task — saves a failed payment to PostgreSQL.
    Retries up to 3 times if DB is unavailable.
    Hot path is never blocked by this.
    """
    try:
        from app.models.db_models import PaymentRecord, PaymentStatusDB
        from datetime import datetime

        db = SessionLocal()
        try:
            # Check if already saved (idempotent)
            existing = db.query(PaymentRecord).filter(
                PaymentRecord.id == payment_data["payment_id"]
            ).first()

            if existing:
                log.info(f"Payment {payment_data['payment_id'][:8]} already in DB — skipping")
                return {"status": "skipped", "reason": "already_exists"}

            record = PaymentRecord(
                id=payment_data["payment_id"],
                amount=payment_data["amount"],
                upi_error_code=payment_data["upi_error_code"],
                error_class=payment_data["error_class"],
                remitter_bank=payment_data["remitter_bank"],
                beneficiary_bank=payment_data["beneficiary_bank"],
                merchant_id=payment_data["merchant_id"],
                merchant_name=payment_data["merchant_name"],
                upi_id=payment_data["upi_id"],
                status=PaymentStatusDB.FAILED,
                retry_count=0,
                failed_at=datetime.fromisoformat(payment_data["failed_at"])
            )

            db.add(record)
            db.commit()

            log.info(f"Async DB write: payment {payment_data['payment_id'][:8]} saved")
            return {"status": "saved", "payment_id": payment_data["payment_id"]}

        finally:
            db.close()

    except Exception as exc:
        log.error(f"Async DB write failed: {exc}. Retrying...")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="app.tasks.db_tasks.save_retry_async"
)
def save_retry_async(self, retry_data: dict):
    """
    Async task — saves a retry attempt to PostgreSQL.
    """
    try:
        from app.models.db_models import RetryAttempt

        db = SessionLocal()
        try:
            attempt = RetryAttempt(
                payment_id=retry_data["payment_id"],
                attempt_number=retry_data["attempt_number"],
                gateway=retry_data["gateway"],
                circuit_state=retry_data.get("circuit_state"),
                delay_seconds=retry_data.get("delay_seconds"),
                status="SCHEDULED",
                notes=retry_data.get("notes")
            )

            db.add(attempt)
            db.commit()

            log.info(
                f"Async DB write: retry attempt "
                f"#{retry_data['attempt_number']} saved"
            )
            return {"status": "saved"}

        finally:
            db.close()

    except Exception as exc:
        log.error(f"Async retry write failed: {exc}. Retrying...")
        raise self.retry(exc=exc)