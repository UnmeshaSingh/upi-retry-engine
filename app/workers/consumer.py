import json
import time
import logging
from datetime import datetime
from app.core.redis_client import get_redis
from app.models.payment import (
    FailedPaymentEvent,
    ErrorClass,
    PaymentStatus,
    UPI_ERROR_CLASS_MAP
)
from app.services.retry_scheduler import (
    get_retry_delay,
    get_max_retries,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# Stream and group config
PAYMENTS_STREAM  = "payments_stream"
CONSUMER_GROUP   = "retry_workers"
CONSUMER_NAME    = "worker_1"
BATCH_SIZE       = 10
BLOCK_MS         = 2000


def ensure_consumer_group(redis):
    try:
        redis.xgroup_create(
            PAYMENTS_STREAM,
            CONSUMER_GROUP,
            id="0",
            mkstream=True
        )
        log.info(f"Consumer group '{CONSUMER_GROUP}' created")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            log.info(f"Consumer group '{CONSUMER_GROUP}' already exists")
        else:
            raise e


def decide_retry_strategy(error_class: str) -> dict:
    """Uses the real retry scheduler with exponential backoff + jitter."""
    delay       = get_retry_delay(error_class, attempt=0)
    max_retries = get_max_retries(error_class)

    return {
        "should_retry":          delay is not None,
        "initial_delay_seconds": delay or 0,
        "max_retries":           max_retries,
        "strategy":              "exponential_backoff_jitter" if delay else "no_retry",
        "reason":                f"Delay: {delay}s | Max retries: {max_retries}"
    }


def process_event(entry_id: str, fields: dict, redis) -> bool:
    payment_id  = fields.get("payment_id")
    error_class = fields.get("error_class")
    upi_error   = fields.get("upi_error_code")
    merchant    = fields.get("merchant_name")
    amount      = fields.get("amount")
    remitter    = fields.get("remitter_bank")
    beneficiary = fields.get("beneficiary_bank")

    if not payment_id or not error_class:
        log.warning(f"Skipping malformed event {entry_id} — missing payment_id or error_class")
        return True

    log.info(f"")
    log.info(f"{'='*60}")
    log.info(f"Processing payment: {payment_id[:8]}...")
    log.info(f"Merchant:          {merchant}")
    log.info(f"Amount:            ₹{amount}")
    log.info(f"UPI Error:         {upi_error}")
    log.info(f"Error Class:       {error_class}")
    log.info(f"Banks:             {remitter} → {beneficiary}")

    strategy = decide_retry_strategy(error_class)

    log.info(f"Decision:          {strategy['reason']}")
    log.info(f"Strategy:          {strategy['strategy']}")

    if strategy["should_retry"]:
        log.info(f"First retry in:    {strategy['initial_delay_seconds']}s")
        log.info(f"Max retries:       {strategy['max_retries']}")

        # Store retry plan in Redis
        retry_key = f"retry_plan:{payment_id}"
        redis.hset(retry_key, mapping={
            "payment_id":      payment_id,
            "strategy":        strategy["strategy"],
            "max_retries":     str(strategy["max_retries"]),
            "next_retry_in":   str(strategy["initial_delay_seconds"]),
            "scheduled_at":    datetime.now().isoformat(),
            "error_class":     error_class,
            "current_attempt": "0"
        })
        redis.expire(retry_key, 86400)
        log.info(f"Retry plan stored: retry_plan:{payment_id[:8]}...")

    else:
        log.info(f"ABANDONED:         Payment will not be retried")

        # Mark as abandoned in Redis
        payment_key = f"payment:{payment_id}"
        data = redis.get(payment_key)
        if data:
            event_dict = json.loads(data)
            event_dict["status"] = PaymentStatus.ABANDONED.value
            redis.set(payment_key, json.dumps(event_dict), ex=86400)

    log.info(f"{'='*60}")
    return True


def run_worker():
    redis = get_redis()

    log.info("Starting UPI Retry Consumer Worker...")
    log.info(f"Stream:         {PAYMENTS_STREAM}")
    log.info(f"Consumer Group: {CONSUMER_GROUP}")
    log.info(f"Consumer Name:  {CONSUMER_NAME}")

    ensure_consumer_group(redis)

    log.info("Worker ready. Waiting for events...")

    while True:
        try:
            messages = redis.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={PAYMENTS_STREAM: ">"},
                count=BATCH_SIZE,
                block=BLOCK_MS
            )

            if not messages:
                continue

            for stream_name, events in messages:
                for entry_id, fields in events:
                    success = process_event(entry_id, fields, redis)

                    if success:
                        redis.xack(PAYMENTS_STREAM, CONSUMER_GROUP, entry_id)
                        log.info(f"ACK: {entry_id}")

        except KeyboardInterrupt:
            log.info("Worker stopped by user")
            break
        except Exception as e:
            log.error(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_worker()