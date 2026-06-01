from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Optional
import uuid


class UPIErrorCode(str, Enum):
    # Remitter bank errors
    U16 = "U16"   # Transaction not permitted
    U30 = "U30"   # Debit freeze on account
    U69 = "U69"   # Remitter bank unavailable
    U70 = "U70"   # Remitter bank timeout

    # Beneficiary bank errors
    Z9  = "Z9"    # Beneficiary bank unavailable
    Z91 = "Z91"   # Beneficiary account invalid

    # NPCI errors
    U43 = "U43"   # Transaction limit exceeded
    U44 = "U44"   # Daily limit exceeded

    # Generic
    U99 = "U99"   # Unknown / other failure


class ErrorClass(str, Enum):
    REMITTER_BANK_DOWN    = "REMITTER_BANK_DOWN"
    BENEFICIARY_BANK_DOWN = "BENEFICIARY_BANK_DOWN"
    ACCOUNT_ISSUE         = "ACCOUNT_ISSUE"
    LIMIT_EXCEEDED        = "LIMIT_EXCEEDED"
    UNKNOWN               = "UNKNOWN"


class PaymentStatus(str, Enum):
    FAILED    = "FAILED"
    RETRYING  = "RETRYING"
    SUCCESS   = "SUCCESS"
    ABANDONED = "ABANDONED"


# Maps each UPI error code to its error class
UPI_ERROR_CLASS_MAP = {
    UPIErrorCode.U16: ErrorClass.ACCOUNT_ISSUE,
    UPIErrorCode.U30: ErrorClass.ACCOUNT_ISSUE,
    UPIErrorCode.U69: ErrorClass.REMITTER_BANK_DOWN,
    UPIErrorCode.U70: ErrorClass.REMITTER_BANK_DOWN,
    UPIErrorCode.Z9:  ErrorClass.BENEFICIARY_BANK_DOWN,
    UPIErrorCode.Z91: ErrorClass.BENEFICIARY_BANK_DOWN,
    UPIErrorCode.U43: ErrorClass.LIMIT_EXCEEDED,
    UPIErrorCode.U44: ErrorClass.LIMIT_EXCEEDED,
    UPIErrorCode.U99: ErrorClass.UNKNOWN,
}


class FailedPaymentEvent(BaseModel):
    payment_id:       str = Field(default_factory=lambda: str(uuid.uuid4()))
    amount:           float = Field(..., gt=0, description="Amount in INR")
    upi_error_code:   UPIErrorCode
    remitter_bank:    str = Field(..., description="Sending bank e.g. HDFC, ICICI")
    beneficiary_bank: str = Field(..., description="Receiving bank e.g. SBI, AXIS")
    merchant_id:      str = Field(..., description="Merchant identifier")
    merchant_name:    str = Field(..., description="e.g. Zomato, Swiggy")
    upi_id:           str = Field(..., description="Recipient UPI ID")
    failed_at:        datetime = Field(default_factory=datetime.utcnow)
    status:           PaymentStatus = PaymentStatus.FAILED
    retry_count:      int = 0


class PaymentEventResponse(BaseModel):
    payment_id:   str
    status:       PaymentStatus
    upi_error_code: UPIErrorCode
    error_class:  ErrorClass
    amount:       float
    merchant_name: str
    retry_count:  int
    failed_at:    datetime
    message:      str