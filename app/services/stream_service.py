import json
from datetime import datetime
from app.core.redis_client import get_redis
from app.models.payment import FailedPaymentEvent, UPI_ERROR_CLASS_MAP

# Stream name
PAYMENTS_STREAM = "payments_stream"

# Maximum stream length — keeps last 10,000 events
MAX_STREAM_LENGTH = 10_000


def push_to_stream(event: FailedPaymentEvent) -> str:
    """
    Push a failed payment event into Redis Stream.
    Returns the stream entry ID assigned by Redis.
    
    * = auto-generate the entry ID (timestamp based)
    MAXLEN = trim stream to last 10,000 entries
    """
    redis = get_redis()

    error_class = UPI_ERROR_CLASS_MAP.get(event.upi_error_code)

    stream_entry = {
        "payment_id":       event.payment_id,
        "amount":           str(event.amount),
        "upi_error_code":   event.upi_error_code.value,
        "error_class":      error_class.value,
        "remitter_bank":    event.remitter_bank,
        "beneficiary_bank": event.beneficiary_bank,
        "merchant_id":      event.merchant_id,
        "merchant_name":    event.merchant_name,
        "upi_id":           event.upi_id,
        "failed_at":        event.failed_at.isoformat(),
        "retry_count":      str(event.retry_count),
        "payload":          event.model_dump_json()
    }

    entry_id = redis.xadd(
        PAYMENTS_STREAM,
        stream_entry,
        maxlen=MAX_STREAM_LENGTH,
        approximate=True
    )

    return entry_id


def read_stream_events(count: int = 10, last_id: str = "0") -> list:
    """
    Read events from the payments stream.
    
    last_id = "0" means read from the beginning
    last_id = "$" means read only new events
    count = how many events to fetch at once
    """
    redis = get_redis()

    results = redis.xrange(
        PAYMENTS_STREAM,
        min=last_id,
        count=count
    )

    events = []
    for entry_id, fields in results:
        events.append({
            "stream_id":      entry_id,
            "payment_id":     fields.get("payment_id"),
            "amount":         fields.get("amount"),
            "upi_error_code": fields.get("upi_error_code"),
            "error_class":    fields.get("error_class"),
            "merchant_name":  fields.get("merchant_name"),
            "remitter_bank":  fields.get("remitter_bank"),
            "beneficiary_bank": fields.get("beneficiary_bank"),
            "failed_at":      fields.get("failed_at"),
            "retry_count":    fields.get("retry_count"),
        })

    return events


def get_stream_length() -> int:
    """Returns total number of events in the stream."""
    redis = get_redis()
    return redis.xlen(PAYMENTS_STREAM)