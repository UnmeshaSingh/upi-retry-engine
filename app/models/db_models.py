from sqlalchemy import (
    Column, String, Float, Integer,
    DateTime, Boolean, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class PaymentStatusDB(str, enum.Enum):
    FAILED    = "FAILED"
    RETRYING  = "RETRYING"
    SUCCESS   = "SUCCESS"
    ABANDONED = "ABANDONED"


class PaymentRecord(Base):
    """Permanent record of every failed payment."""
    __tablename__ = "payments"

    id               = Column(String, primary_key=True)  # UUID
    amount           = Column(Float, nullable=False)
    upi_error_code   = Column(String(10), nullable=False)
    error_class      = Column(String(50), nullable=False)
    remitter_bank    = Column(String(20), nullable=False)
    beneficiary_bank = Column(String(20), nullable=False)
    merchant_id      = Column(String(50), nullable=False)
    merchant_name    = Column(String(100), nullable=False)
    upi_id           = Column(String(100), nullable=False)
    status           = Column(
        SAEnum(PaymentStatusDB),
        default=PaymentStatusDB.FAILED,
        nullable=False
    )
    retry_count      = Column(Integer, default=0)
    failed_at        = Column(DateTime, nullable=False)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationship to retry attempts
    retry_attempts = relationship("RetryAttempt", back_populates="payment")

    def __repr__(self):
        return f"<Payment {self.id[:8]} {self.merchant_name} ₹{self.amount} {self.status}>"


class RetryAttempt(Base):
    """Record of every retry attempt for a payment."""
    __tablename__ = "retry_attempts"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    payment_id     = Column(String, ForeignKey("payments.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    gateway        = Column(String(20), nullable=False)
    circuit_state  = Column(String(20), nullable=True)
    delay_seconds  = Column(Float, nullable=True)
    status         = Column(String(20), default="SCHEDULED")
    error_code     = Column(String(10), nullable=True)
    attempted_at   = Column(DateTime, server_default=func.now())
    notes          = Column(Text, nullable=True)

    # Relationship back to payment
    payment = relationship("PaymentRecord", back_populates="retry_attempts")

    def __repr__(self):
        return f"<RetryAttempt #{self.attempt_number} payment={self.payment_id[:8]}>"


class SLABreachRecord(Base):
    """Record of every SLA breach."""
    __tablename__ = "sla_breaches"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    payment_id     = Column(String, nullable=False)
    merchant_id    = Column(String(50), nullable=False)
    merchant_name  = Column(String(100), nullable=False)
    sla_seconds    = Column(Integer, nullable=False)
    elapsed_seconds = Column(Float, nullable=False)
    breached_at    = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<SLABreach {self.merchant_name} {self.elapsed_seconds}s>"