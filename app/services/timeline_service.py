import json
import logging
from datetime import datetime
from typing import List
from app.core.redis_client import get_redis
from app.models.payment import TimelineEvent, TimelineEventType

log = logging.getLogger(__name__)

# Redis key pattern
TIMELINE_KEY = "timeline:{payment_id}"
TIMELINE_TTL = 86400  # 24 hours


def add_timeline_event(payment_id: str, event: TimelineEvent):
    """
    Append an event to the payment timeline.
    Timeline is stored as a Redis List — each entry is a JSON string.
    """
    redis = get_redis()
    key = TIMELINE_KEY.format(payment_id=payment_id)

    # Serialize event
    event_data = event.model_dump()
    event_data["timestamp"] = event.timestamp.isoformat()
    event_data["event_type"] = event.event_type.value

    redis.rpush(key, json.dumps(event_data))
    redis.expire(key, TIMELINE_TTL)

    log.info(f"Timeline [{payment_id[:8]}]: {event.event_type.value} — {event.message}")


def get_timeline(payment_id: str) -> List[dict]:
    """
    Get full timeline for a payment.
    Returns events in chronological order.
    """
    redis = get_redis()
    key = TIMELINE_KEY.format(payment_id=payment_id)

    # LRANGE 0 -1 = get all entries
    raw_events = redis.lrange(key, 0, -1)

    events = []
    for raw in raw_events:
        events.append(json.loads(raw))

    return events


def record_payment_failed(
    payment_id: str,
    error_code: str,
    gateway: str,
    merchant: str,
    amount: float
):
    """Record the initial payment failure."""
    add_timeline_event(payment_id, TimelineEvent(
        event_type=TimelineEventType.PAYMENT_FAILED,
        gateway=gateway,
        error_code=error_code,
        message=f"Payment of ₹{amount} to {merchant} failed with {error_code} on {gateway}"
    ))


def record_retry_scheduled(
    payment_id: str,
    attempt: int,
    delay_seconds: float,
    gateway: str,
    circuit_state: str,
    retry_at: str
):
    """Record that a retry has been scheduled."""
    add_timeline_event(payment_id, TimelineEvent(
        event_type=TimelineEventType.RETRY_SCHEDULED,
        gateway=gateway,
        circuit_state=circuit_state,
        delay_seconds=delay_seconds,
        attempt_number=attempt,
        message=f"Retry #{attempt} scheduled via {gateway} in {delay_seconds}s (circuit: {circuit_state}) — retry_at: {retry_at}"
    ))


def record_gateway_switched(
    payment_id: str,
    from_gateway: str,
    to_gateway: str,
    reason: str
):
    """Record a gateway switch."""
    add_timeline_event(payment_id, TimelineEvent(
        event_type=TimelineEventType.GATEWAY_SWITCHED,
        gateway=to_gateway,
        message=f"Gateway switched: {from_gateway} → {to_gateway} — reason: {reason}"
    ))


def record_circuit_tripped(
    payment_id: str,
    gateway: str,
    failure_count: int
):
    """Record a circuit breaker trip."""
    add_timeline_event(payment_id, TimelineEvent(
        event_type=TimelineEventType.CIRCUIT_TRIPPED,
        gateway=gateway,
        circuit_state="OPEN",
        message=f"Circuit breaker TRIPPED on {gateway} after {failure_count} failures"
    ))


def record_abandoned(payment_id: str, reason: str):
    """Record payment abandonment."""
    add_timeline_event(payment_id, TimelineEvent(
        event_type=TimelineEventType.ABANDONED,
        message=f"Payment abandoned — {reason}"
    ))