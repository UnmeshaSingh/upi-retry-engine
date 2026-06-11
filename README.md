# UPI Retry Engine

> Most payment systems retry blindly. This one doesn't.

A production-grade payment retry orchestration engine built around 
real UPI failure taxonomy. When a payment fails, the engine classifies 
the error using NPCI error codes, selects the best available gateway, 
checks circuit breaker state, applies exponential backoff with full 
jitter, and schedules intelligent retries — all within milliseconds.

---

## Benchmark

| Metric | Result |
|--------|--------|
| Throughput | **80 RPS** sustained |
| Median latency | **9ms** |
| p99 latency | **130ms** |
| Concurrent users | **100** |
| Failure rate | **0%** |
| Test duration | 3 minutes, 5,700+ requests |

Load tested with Locust across a mixed workload: payment failures, 
timeline reads, circuit breaker checks, and gateway routing queries.

---

## The Problem

UPI processes ~10 billion transactions per month in India. When a 
payment fails, naive systems retry on the same gateway with fixed 
delays. This causes:

- **Thundering herd** — all failed payments retry simultaneously, 
  overwhelming recovering banks
- **Wasted retries** — retrying a frozen account (U30) is pointless; 
  retrying a temporarily down bank (U69) is essential
- **SLA breaches** — Zomato's order cancels if payment isn't confirmed 
  in 8 seconds; a generic retry engine doesn't know this

This engine solves all three.

---

## Architecture

POST /payments/fail
│
▼
FastAPI App ──────────────────────────────────────────┐
│                                                 │
├─► Redis (payment store, 24hr TTL)               │
├─► PostgreSQL (permanent audit log)              │
└─► Redis Stream (payments_stream)                │
│                                     │
▼                                     │
Consumer Worker                               │
│                                     │
├─► UPI Error Classification          │
├─► SLA Priority Scoring              │
├─► Circuit Breaker Check             │
├─► Gateway Routing (best available)  │
├─► Exponential Backoff + Jitter      │
└─► Timeline Event Recording          │
│
GET /payments/{id}/timeline ◄──────────────────────────┘

---

## Key Features

**UPI-Aware Error Classification**
Maps real NPCI error codes to retry strategies. U69 (remitter bank 
unavailable) triggers exponential backoff with 5 retries. U30 
(account frozen) is abandoned immediately — retrying won't help. 
Z9 (beneficiary bank down) gets a longer initial delay and fewer 
retries.

**Exponential Backoff with Full Jitter**
Implements AWS's recommended full jitter algorithm: 
`delay = random(0, min(max_delay, base_delay × 2^attempt))`. 
Full jitter prevents thundering herd by spreading retries randomly 
across the backoff window instead of retrying in synchronized waves.

**Three-State Circuit Breaker**
Per-gateway circuit breaker with CLOSED → OPEN → HALF_OPEN state 
machine. Trips after 5 failures in a window. After 60s recovery 
timeout, moves to HALF_OPEN and allows one test request. Two 
consecutive successes close the circuit. Single failure in HALF_OPEN 
reopens immediately.

**Intelligent Gateway Routing**
Five PSP gateways with priority ordering. Tracks success rate per 
gateway per 5-minute window using Redis counters. Auto-switches to 
next priority gateway when primary fails. Integrates circuit breaker 
state into routing decisions.

**Merchant SLA Awareness**
Each merchant has a configurable SLA deadline. Zomato: 8 seconds 
(order cancels). Swiggy: 12 seconds. Amazon: 30 seconds. Priority 
score combines merchant base priority with SLA urgency — a Zomato 
payment at 87% of its SLA window scores 800 vs Myntra at 1.7% 
scoring 200.

**Full Payment Timeline**
Every payment has a complete audit trail stored in Redis as an 
ordered list. Records: initial failure, gateway switch, circuit 
state at routing time, each scheduled retry with exact timestamp, 
and final disposition (retrying/abandoned).

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + Pydantic |
| Event Queue | Redis Streams |
| Cache | Redis |
| Database | PostgreSQL + SQLAlchemy |
| Worker | Python (consumer group) |
| Load Testing | Locust |
| Containerization | Docker + Docker Compose |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/payments/fail` | Report a failed payment |
| GET | `/payments/{id}/timeline` | Full retry audit trail |
| GET | `/payments/history/all` | PostgreSQL payment history |
| GET | `/routing/status` | Live gateway health |
| GET | `/routing/best` | Best available gateway |
| GET | `/circuit-breaker/status` | All circuit states |
| GET | `/circuit-breaker/can-pass/{bank}` | Request gating |
| GET | `/retry/plan/{id}` | Full retry schedule |
| GET | `/retry/simulate/{error_class}` | Backoff simulation |
| GET | `/merchants/sla` | Merchant SLA registry |

---

## UPI Error Code Taxonomy

| Code | Meaning | Strategy |
|------|---------|----------|
| U69 | Remitter bank unavailable | Exponential backoff, 5 retries |
| Z9 | Beneficiary bank unavailable | Exponential backoff, 3 retries |
| U30 | Account frozen/debit freeze | Abandoned immediately |
| U16 | Transaction not permitted | Abandoned immediately |
| U44 | Daily limit exceeded | Fixed delay, retry after 1hr |
| U43 | Transaction limit exceeded | Fixed delay, 2 retries |
| U99 | Unknown failure | Exponential backoff, 2 retries |

---

## Why This Exists

Real UPI infrastructure at companies like Razorpay, PhonePe, and 
Cashfree faces exactly these problems at scale. During peak hours 
(8–10pm IST), UPI failure rates spike — often concentrated on 
specific PSP gateways. A retry engine that doesn't understand 
failure taxonomy, gateway health, or merchant SLAs will make 
outages worse, not better.

This project models the core retry orchestration layer that sits 
between a payment gateway failure and the decision of what to do next.

---

## Running Locally

```bash
# Clone and setup
git clone https://github.com/UnmeshaSingh/upi-retry-engine.git
cd upi-retry-engine
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Start Redis (requires Memurai on Windows or Redis on Linux/Mac)
# Start PostgreSQL and create database: upi_retry_db

# Run the API
uvicorn app.main:app --reload

# Run the worker (separate terminal)
python -m app.workers.consumer

# Run load tests
locust -f locustfile.py --host=http://127.0.0.1:8000
```

Or with Docker:
```bash
docker-compose up --build
```

---

## Why This Bottlenecks at Scale

Under 500 concurrent users, p99 latency spikes to ~90s. The 
bottleneck is PostgreSQL write contention on `/payments/fail` — 
every request synchronously writes to two storage layers. 

Production fix: move the PostgreSQL write to an async Celery task, 
keeping the hot path Redis-only. The timeline endpoint also suffers 
under high concurrency because Locust generates unique payment IDs 
per user — in production, repeated reads of the same payment ID 
would benefit from Redis caching the timeline.

---

*Built as a portfolio project targeting fintech infrastructure roles.*