import time
import logging
from enum import Enum
from typing import Optional
from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

# ── Circuit breaker config ────────────────────────────────────────────────────

class CircuitState(str, Enum):
    CLOSED    = "CLOSED"      # Normal — requests flow through
    OPEN      = "OPEN"        # Tripped — requests blocked
    HALF_OPEN = "HALF_OPEN"   # Testing — one request allowed through


# How many failures to trip the circuit
FAILURE_THRESHOLD = 5

# How long circuit stays OPEN before moving to HALF_OPEN (seconds)
RECOVERY_TIMEOUT = 60

# How many successes in HALF_OPEN to move back to CLOSED
SUCCESS_THRESHOLD = 2

# Redis key patterns
CB_STATE_KEY    = "cb:state:{bank}"
CB_FAILURES_KEY = "cb:failures:{bank}"
CB_SUCCESSES_KEY = "cb:successes:{bank}"
CB_OPENED_AT_KEY = "cb:opened_at:{bank}"


# ── Core circuit breaker logic ────────────────────────────────────────────────

def get_circuit_state(bank: str) -> CircuitState:
    """
    Get current circuit state for a gateway.
    Handles OPEN → HALF_OPEN transition automatically based on timeout.
    """
    redis = get_redis()
    state_key = CB_STATE_KEY.format(bank=bank)
    state = redis.get(state_key)

    if not state:
        return CircuitState.CLOSED

    if state == CircuitState.OPEN:
        # Check if recovery timeout has passed
        opened_at_key = CB_OPENED_AT_KEY.format(bank=bank)
        opened_at = redis.get(opened_at_key)

        if opened_at:
            elapsed = time.time() - float(opened_at)
            if elapsed >= RECOVERY_TIMEOUT:
                # Transition to HALF_OPEN
                _set_state(bank, CircuitState.HALF_OPEN)
                log.info(f"Circuit {bank}: OPEN → HALF_OPEN (elapsed: {elapsed:.1f}s)")
                return CircuitState.HALF_OPEN

    return CircuitState(state)


def _set_state(bank: str, state: CircuitState):
    """Set circuit state in Redis."""
    redis = get_redis()
    state_key = CB_STATE_KEY.format(bank=bank)
    redis.set(state_key, state.value, ex=3600)  # 1hr TTL
    log.info(f"Circuit {bank}: state → {state.value}")


def record_success(bank: str):
    """
    Record a successful call.
    In HALF_OPEN: accumulate successes → if enough, close circuit.
    In CLOSED: reset failure count.
    """
    redis = get_redis()
    state = get_circuit_state(bank)

    if state == CircuitState.HALF_OPEN:
        # Increment success count
        success_key = CB_SUCCESSES_KEY.format(bank=bank)
        successes = redis.incr(success_key)
        redis.expire(success_key, 300)

        log.info(f"Circuit {bank}: HALF_OPEN success {successes}/{SUCCESS_THRESHOLD}")

        if successes >= SUCCESS_THRESHOLD:
            # Enough successes — close the circuit
            _close_circuit(bank)

    elif state == CircuitState.CLOSED:
        # Reset failure count on success
        failure_key = CB_FAILURES_KEY.format(bank=bank)
        redis.delete(failure_key)


def record_failure(bank: str):
    """
    Record a failed call.
    In CLOSED: accumulate failures → if enough, open circuit.
    In HALF_OPEN: single failure → back to OPEN.
    """
    redis = get_redis()
    state = get_circuit_state(bank)

    if state == CircuitState.HALF_OPEN:
        # Any failure in HALF_OPEN → immediately back to OPEN
        log.warning(f"Circuit {bank}: HALF_OPEN failure → reopening")
        _open_circuit(bank)

    elif state == CircuitState.CLOSED:
        failure_key = CB_FAILURES_KEY.format(bank=bank)
        failures = redis.incr(failure_key)
        redis.expire(failure_key, 300)

        log.info(f"Circuit {bank}: failure {failures}/{FAILURE_THRESHOLD}")

        if failures >= FAILURE_THRESHOLD:
            _open_circuit(bank)


def _open_circuit(bank: str):
    """Trip the circuit — move to OPEN state."""
    redis = get_redis()

    _set_state(bank, CircuitState.OPEN)

    # Record when it was opened
    opened_at_key = CB_OPENED_AT_KEY.format(bank=bank)
    redis.set(opened_at_key, str(time.time()), ex=3600)

    # Reset counters
    redis.delete(CB_FAILURES_KEY.format(bank=bank))
    redis.delete(CB_SUCCESSES_KEY.format(bank=bank))

    log.warning(f"Circuit OPENED: {bank} — will retry in {RECOVERY_TIMEOUT}s")


def _close_circuit(bank: str):
    """Close the circuit — back to normal."""
    redis = get_redis()

    _set_state(bank, CircuitState.CLOSED)

    # Clear all counters
    redis.delete(CB_FAILURES_KEY.format(bank=bank))
    redis.delete(CB_SUCCESSES_KEY.format(bank=bank))
    redis.delete(CB_OPENED_AT_KEY.format(bank=bank))

    log.info(f"Circuit CLOSED: {bank} — fully recovered")


def can_pass_request(bank: str) -> bool:
    """
    Returns True if a request can be sent to this gateway.
    CLOSED → yes
    OPEN → no
    HALF_OPEN → yes (one test request allowed)
    """
    state = get_circuit_state(bank)

    if state == CircuitState.CLOSED:
        return True
    elif state == CircuitState.OPEN:
        return False
    elif state == CircuitState.HALF_OPEN:
        return True

    return False


def get_circuit_status(bank: str) -> dict:
    """Get full circuit breaker status for a gateway."""
    redis = get_redis()
    state = get_circuit_state(bank)

    failure_key  = CB_FAILURES_KEY.format(bank=bank)
    success_key  = CB_SUCCESSES_KEY.format(bank=bank)
    opened_at_key = CB_OPENED_AT_KEY.format(bank=bank)

    failures  = int(redis.get(failure_key) or 0)
    successes = int(redis.get(success_key) or 0)
    opened_at = redis.get(opened_at_key)

    time_until_half_open = None
    if state == CircuitState.OPEN and opened_at:
        elapsed = time.time() - float(opened_at)
        remaining = max(0, RECOVERY_TIMEOUT - elapsed)
        time_until_half_open = round(remaining, 1)

    return {
        "bank":                   bank,
        "state":                  state.value,
        "failures":               failures,
        "successes_in_half_open": successes,
        "failure_threshold":      FAILURE_THRESHOLD,
        "success_threshold":      SUCCESS_THRESHOLD,
        "recovery_timeout":       RECOVERY_TIMEOUT,
        "can_accept_requests":    can_pass_request(bank),
        "time_until_half_open":   f"{time_until_half_open}s" if time_until_half_open else None,
    }


def get_all_circuit_status() -> list:
    """Get circuit breaker status for all gateways."""
    from app.services.routing_service import GATEWAY_REGISTRY
    return [get_circuit_status(bank) for bank in GATEWAY_REGISTRY]