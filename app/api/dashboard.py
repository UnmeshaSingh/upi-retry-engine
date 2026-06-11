from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.services.circuit_breaker import get_all_circuit_status
from app.services.routing_service import get_all_gateway_status
from app.services.stream_service import get_stream_length
from app.services.peak_hour_service import get_system_status
from app.core.redis_client import get_redis

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/data")
def dashboard_data():
    """JSON data endpoint for the dashboard."""
    redis = get_redis()

    # Get all data
    circuits       = get_all_circuit_status()
    gateways       = get_all_gateway_status()
    stream_length  = get_stream_length()
    system_status  = get_system_status()

    # Count payments by status
    payment_keys = redis.keys("payment:*")
    retry_keys   = redis.keys("retry_plan:*")
    breach_keys  = redis.keys("sla_breach:*")

    return {
        "circuits":      circuits,
        "gateways":      gateways,
        "stream_length": stream_length,
        "system":        system_status,
        "counts": {
            "total_payments":  len(payment_keys),
            "active_retries":  len(retry_keys),
            "sla_breaches":    len(breach_keys),
        }
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Live admin dashboard."""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UPI Retry Engine — Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', monospace;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 24px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #222;
        }

        .header h1 {
            font-size: 20px;
            color: #00ff88;
            letter-spacing: 2px;
        }

        .header .meta {
            font-size: 12px;
            color: #555;
        }

        .last-update {
            font-size: 11px;
            color: #444;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
            margin-bottom: 16px;
        }

        .card {
            background: #111;
            border: 1px solid #222;
            border-radius: 8px;
            padding: 16px;
        }

        .card h2 {
            font-size: 11px;
            color: #555;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }

        /* Metrics row */
        .metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 16px;
        }

        .metric {
            background: #111;
            border: 1px solid #222;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }

        .metric .value {
            font-size: 28px;
            font-weight: bold;
            color: #00ff88;
            display: block;
        }

        .metric .label {
            font-size: 11px;
            color: #555;
            margin-top: 4px;
            letter-spacing: 1px;
        }

        /* Gateway rows */
        .gateway-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #1a1a1a;
        }

        .gateway-row:last-child { border-bottom: none; }

        .gateway-name {
            font-size: 13px;
            font-weight: bold;
            min-width: 60px;
        }

        .gateway-stats {
            font-size: 11px;
            color: #555;
            flex: 1;
            padding: 0 12px;
        }

        /* Circuit state badges */
        .state-badge {
            font-size: 10px;
            padding: 3px 8px;
            border-radius: 4px;
            letter-spacing: 1px;
            font-weight: bold;
        }

        .state-CLOSED {
            background: rgba(0,255,136,0.15);
            color: #00ff88;
            border: 1px solid rgba(0,255,136,0.3);
        }

        .state-OPEN {
            background: rgba(255,80,80,0.15);
            color: #ff5050;
            border: 1px solid rgba(255,80,80,0.3);
        }

        .state-HALF_OPEN {
            background: rgba(255,200,0,0.15);
            color: #ffc800;
            border: 1px solid rgba(255,200,0,0.3);
        }

        /* System status */
        .status-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #1a1a1a;
            font-size: 12px;
        }

        .status-row:last-child { border-bottom: none; }

        .status-key { color: #555; }

        .status-val { color: #e0e0e0; }

        .val-green { color: #00ff88; }
        .val-red   { color: #ff5050; }
        .val-yellow { color: #ffc800; }

        /* Stream indicator */
        .stream-bar {
            background: #1a1a1a;
            border-radius: 4px;
            height: 8px;
            margin-top: 8px;
            overflow: hidden;
        }

        .stream-fill {
            background: #00ff88;
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }

        /* Spike alert */
        .spike-alert {
            background: rgba(255,80,80,0.1);
            border: 1px solid rgba(255,80,80,0.3);
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 16px;
            display: none;
            font-size: 13px;
            color: #ff5050;
        }

        .spike-alert.active { display: block; }

        /* Throttle indicator */
        .throttle-badge {
            display: inline-block;
            background: rgba(255,200,0,0.15);
            border: 1px solid rgba(255,200,0,0.3);
            color: #ffc800;
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 4px;
            margin-left: 8px;
        }

        .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }

        .dot-green  { background: #00ff88; animation: pulse 2s infinite; }
        .dot-red    { background: #ff5050; }
        .dot-yellow { background: #ffc800; }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        .footer {
            margin-top: 24px;
            text-align: center;
            font-size: 11px;
            color: #333;
        }
    </style>
</head>
<body>

<div class="header">
    <h1>⚡ UPI RETRY ENGINE</h1>
    <div class="meta">
        <div>github.com/UnmeshaSingh/upi-retry-engine</div>
        <div class="last-update" id="lastUpdate">Connecting...</div>
    </div>
</div>

<!-- Spike Alert -->
<div class="spike-alert" id="spikeAlert">
    ⚠ FAILURE SPIKE DETECTED — Retry throttling active
    <span class="throttle-badge" id="throttleBadge"></span>
</div>

<!-- Key Metrics -->
<div class="metrics">
    <div class="metric">
        <span class="value" id="totalPayments">—</span>
        <span class="label">PAYMENTS IN REDIS</span>
    </div>
    <div class="metric">
        <span class="value" id="streamLength">—</span>
        <span class="label">STREAM QUEUE DEPTH</span>
    </div>
    <div class="metric">
        <span class="value" id="activeRetries">—</span>
        <span class="label">ACTIVE RETRY PLANS</span>
    </div>
</div>

<div class="grid">
    <!-- Gateway Health -->
    <div class="card">
        <h2>Gateway Health</h2>
        <div id="gatewayList">Loading...</div>
    </div>

    <!-- Circuit Breakers -->
    <div class="card">
        <h2>Circuit Breakers</h2>
        <div id="circuitList">Loading...</div>
    </div>

    <!-- System Status -->
    <div class="card">
        <h2>System Status</h2>
        <div id="systemStatus">Loading...</div>
    </div>
</div>

<div class="footer">
    Auto-refreshes every 5 seconds &nbsp;·&nbsp;
    <span id="dotIndicator"><span class="dot dot-green"></span>LIVE</span>
</div>

<script>
    async function fetchData() {
        try {
            const res  = await fetch('/dashboard/data');
            const data = await res.json();
            updateDashboard(data);
            document.getElementById('lastUpdate').textContent =
                'Last update: ' + new Date().toLocaleTimeString();
        } catch (e) {
            document.getElementById('lastUpdate').textContent = 'Error fetching data';
        }
    }

    function updateDashboard(data) {
        // Metrics
        document.getElementById('totalPayments').textContent =
            data.counts.total_payments;
        document.getElementById('streamLength').textContent =
            data.stream_length;
        document.getElementById('activeRetries').textContent =
            data.counts.active_retries;

        // Spike alert
        const spikeAlert = document.getElementById('spikeAlert');
        if (data.system.spike_detected) {
            spikeAlert.classList.add('active');
            document.getElementById('throttleBadge').textContent =
                'Retry probability: ' + data.system.retry_probability;
        } else {
            spikeAlert.classList.remove('active');
        }

        // Gateways
        const gwHtml = data.gateways.map(gw => `
            <div class="gateway-row">
                <div class="gateway-name">${gw.bank}</div>
                <div class="gateway-stats">
                    ${gw.attempts} req · ${gw.success_rate} success
                </div>
                <div>
                    ${gw.blocked
                        ? '<span class="state-badge state-OPEN">BLOCKED</span>'
                        : '<span class="state-badge state-CLOSED">HEALTHY</span>'
                    }
                </div>
            </div>
        `).join('');
        document.getElementById('gatewayList').innerHTML = gwHtml;

        // Circuits
        const cbHtml = data.circuits.map(cb => {
            const stateClass = 'state-' + cb.state;
            const extra = cb.state === 'OPEN'
                ? ` · ${cb.time_until_half_open || '?'} to HALF_OPEN`
                : cb.state === 'HALF_OPEN'
                ? ` · ${cb.successes_in_half_open}/${cb.success_threshold} ok`
                : ` · ${cb.failures}/${cb.failure_threshold} fails`;
            return `
                <div class="gateway-row">
                    <div class="gateway-name">${cb.bank}</div>
                    <div class="gateway-stats" style="font-size:10px">
                        ${extra}
                    </div>
                    <span class="state-badge ${stateClass}">${cb.state}</span>
                </div>
            `;
        }).join('');
        document.getElementById('circuitList').innerHTML = cbHtml;

        // System status
        const sys = data.system;
        const rows = [
            ['Time (IST)',      sys.current_time_ist, ''],
            ['Peak Hour',       sys.is_peak_hour ? 'YES' : 'NO',
                                sys.is_peak_hour ? 'val-yellow' : 'val-green'],
            ['Spike Detected',  sys.spike_detected ? 'YES' : 'NO',
                                sys.spike_detected ? 'val-red' : 'val-green'],
            ['Throttle Active', sys.throttle_active ? 'YES' : 'NO',
                                sys.throttle_active ? 'val-yellow' : 'val-green'],
            ['Retry Probability', sys.retry_probability,
                                sys.throttle_active ? 'val-yellow' : 'val-green'],
            ['Failures/min',    sys.failures_this_minute, ''],
            ['SLA Breaches',    data.counts.sla_breaches,
                                data.counts.sla_breaches > 0 ? 'val-red' : 'val-green'],
        ];

        const sysHtml = rows.map(([key, val, cls]) => `
            <div class="status-row">
                <span class="status-key">${key}</span>
                <span class="status-val ${cls}">${val}</span>
            </div>
        `).join('');
        document.getElementById('systemStatus').innerHTML = sysHtml;
    }

    // Initial fetch
    fetchData();

    // Auto-refresh every 5 seconds
    setInterval(fetchData, 5000);
</script>

</body>
</html>
"""
    return HTMLResponse(content=html)