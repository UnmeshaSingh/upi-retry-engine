# UPI Retry Engine — Resume Bullets + Interview Prep

---

## Resume Bullets

### Primary Bullet (use this one — it's the stopper)

> Built a UPI-aware payment retry orchestration engine (FastAPI + Redis Streams + PostgreSQL) with NPCI error-code-specific retry strategies (U69/Z9/U30), three-state circuit breakers per gateway, exponential backoff with full jitter, and merchant SLA-aware prioritisation — benchmarked at 80 RPS, p99 130ms, 0% failures under 100 concurrent users

---

### Secondary Bullets (pick 2-3 for sub-points)

> Implemented exponential backoff with full jitter — `delay = random(0, min(cap, base × 2^n))` — preventing thundering herd on bank recovery; same algorithm used by AWS SQS and Stripe

> Built a three-state circuit breaker (CLOSED → OPEN → HALF_OPEN) per payment gateway with configurable failure threshold, recovery timeout, and automatic state transitions stored in Redis with TTL

> Designed intelligent gateway routing table tracking per-PSP success rates in 5-minute sliding windows using Redis INCR; auto-failover routes to next priority gateway when failure rate exceeds threshold

> Modelled merchant SLA deadlines (Zomato 8s, Swiggy 12s, Amazon 30s) with real-time priority scoring — payments near SLA breach score 4x higher in the retry queue than low-urgency orders

> Implemented dual storage architecture — Redis for sub-millisecond hot path with 24hr TTL, PostgreSQL for permanent audit log — with complete per-payment timeline recording every retry decision, gateway switch, and circuit state

---

### How to Structure It on Your Resume

```
UPI Retry Orchestration Engine                    github.com/UnmeshaSingh/upi-retry-engine
• Built a UPI-aware payment retry engine (FastAPI + Redis Streams + PostgreSQL) with
  NPCI error-code-specific strategies, circuit breakers, exponential backoff + full
  jitter, and SLA-aware prioritisation — 80 RPS, p99 130ms, 0% failures
• Implemented three-state circuit breaker per gateway (CLOSED/OPEN/HALF_OPEN) with
  auto-failover routing to next priority PSP on failure threshold breach
• Dual storage: Redis hot path (sub-ms reads) + PostgreSQL audit log with full
  per-payment retry timeline
```

---

## Interview Questions + Answers

### Q: Why exponential backoff instead of fixed delay?

Fixed delay means all failed payments retry at the same time — if 10,000 payments fail during a bank outage, they all retry 30 seconds later and overwhelm the recovering bank again. Exponential backoff spreads retries out over time. Full jitter goes further — it randomizes the delay within the exponential window so even concurrent failures don't synchronize their retries.

---

### Q: What's the difference between your routing table and the circuit breaker? Aren't they doing the same thing?

They operate at different granularities. The routing table tracks success rates in a time window and makes routing decisions — it's proactive, always selecting the best available gateway. The circuit breaker is reactive — it monitors individual gateway health and completely stops traffic when a gateway is clearly failing. The routing table answers "which gateway should I use?" The circuit breaker answers "is this gateway even safe to try?"

---

### Q: Why Redis Streams instead of a simple Redis List?

Redis Lists don't have consumer groups. If I have multiple worker instances, a simple LPUSH/BRPOP setup would deliver the same event to multiple workers — duplicate processing. Redis Streams with consumer groups guarantee each event is delivered to exactly one worker. If a worker crashes mid-processing, the event stays in a pending state and gets reclaimed by another worker. That's at-least-once delivery guarantee, which you need in a payment system.

---

### Q: What happens when PostgreSQL is down?

Currently the PostgreSQL write is synchronous in the hot path — if Postgres is down, the entire `/payments/fail` endpoint fails. The correct production fix is to move the Postgres write to an async Celery task. Redis write succeeds first, stream push succeeds, worker processes the event — Postgres write happens asynchronously. The payment is retried even if the audit log temporarily fails. I documented this as a known limitation in the README.

---

### Q: How does your SLA system actually affect retry order?

Each payment gets a priority score combining the merchant's base priority and how close the payment is to SLA breach. A Zomato payment at 87% of its 8-second window scores 800. A Myntra payment at 1% of its 300-second window scores 200. In a real priority queue implementation, higher score payments would be dequeued first. Right now the score is calculated and stored — the actual priority queue ordering would be the next feature to build.

---

### Q: What's the thundering herd problem and how does your jitter solve it?

When a bank has an outage, thousands of payments fail simultaneously. Without jitter, they all have the same retry schedule — they all retry at T+30s, then T+60s, then T+120s, hitting the recovering bank in synchronized waves. Each wave can re-trigger the outage. Full jitter randomizes each delay within the exponential window — instead of all retrying at exactly 30 seconds, they retry randomly between 0 and 30 seconds. The load on the recovering bank is spread smoothly instead of arriving in spikes.

---

### Q: Why did your p99 spike to 90 seconds under 500 users?

Two reasons. First, PostgreSQL write contention — every `/payments/fail` request synchronously writes to two storage layers. Under high concurrency, Postgres connection pool gets exhausted and requests queue up. Second, Locust generates a unique payment ID per user for GET requests, so there's no cache hit benefit — every timeline read hits Redis with a cold key. In production, repeated reads of the same payment would benefit from in-memory caching. The fix is async Postgres writes via Celery and connection pool tuning.

---

## The One Question That Trips Everyone Up

### Q: Walk me through exactly what happens when I call POST /payments/fail with U69.

Practice saying this out loud until smooth:

> "The request hits FastAPI which validates the payload using Pydantic. The UPI error code U69 maps to error class REMITTER_BANK_DOWN. The payment gets stored in Redis with a 24-hour TTL and written to PostgreSQL permanently. Then it's pushed into a Redis Stream. The consumer worker, running in a separate process with a consumer group, picks it up within 2 seconds. It calls the SLA service to check if this merchant's deadline is at risk. Then it checks the circuit breaker — if the remitter bank's circuit is OPEN, it routes to the next priority gateway instead. It calculates the retry schedule using exponential backoff with full jitter — for REMITTER_BANK_DOWN that's 5 attempts with base delay 30 seconds, capped at 10 minutes. Each attempt is written to the payment timeline in Redis. The worker acknowledges the stream event. Now GET /payments/{id}/timeline returns the full story — original failure on HDFC, gateway switch to ICICI, 5 scheduled retries with exact timestamps."

That answer takes 90 seconds. Practice it until you can say it without looking at notes.

---

## UPI Error Code Cheat Sheet

| Code | Meaning | Your Strategy |
|------|---------|--------------|
| U69 | Remitter bank unavailable | Exponential backoff, 5 retries, base 30s |
| Z9 | Beneficiary bank unavailable | Exponential backoff, 3 retries, base 60s |
| U30 | Account frozen / debit freeze | Abandoned immediately — retrying won't help |
| U16 | Transaction not permitted | Abandoned immediately |
| U44 | Daily limit exceeded | Fixed delay, retry after 1 hour |
| U43 | Transaction limit exceeded | Fixed delay, 2 retries |
| U99 | Unknown failure | Exponential backoff, 2 retries, cautious |

---

## Key Numbers to Memorize

- **80 RPS** sustained under 100 concurrent users
- **9ms** median latency
- **130ms** p99 latency
- **0%** failure rate
- **5,700+** requests in 3-minute test
- **5** gateways in routing table
- **5** failure threshold to trip circuit breaker
- **60s** recovery timeout before HALF_OPEN
- **2** successes needed to close circuit from HALF_OPEN
- **24hr** Redis TTL on payment events
- **10,000** max stream length (MAXLEN trimming)

---

## Domain Vocabulary to Use in Interviews

Use these words naturally — they signal you know the space:

- **PSP** (Payment Service Provider) — not just "gateway"
- **NPCI** — National Payments Corporation of India
- **Remitter bank** — sending bank (not "source bank")
- **Beneficiary bank** — receiving bank (not "destination bank")
- **Thundering herd** — synchronized retry storm
- **Consumer group** — Redis Streams delivery guarantee
- **At-least-once delivery** — event processing guarantee
- **Hot path** — latency-critical code path (Redis reads)
- **Cold path** — non-latency-critical (Postgres writes)
- **SLA** — Service Level Agreement (merchant deadline)
- **Circuit tripped** — circuit breaker moved to OPEN state

---

*Study this before every fintech interview. Know the numbers. Practice the walk-through answer.*