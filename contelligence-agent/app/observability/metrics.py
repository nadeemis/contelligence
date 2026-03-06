"""Custom OpenTelemetry metrics for the HikmaForge agent.

All metrics are registered under the ``contelligence.agent`` meter and
use descriptive names under the ``contelligence.`` namespace so they are
easy to identify in Application Insights custom metrics.
"""

from __future__ import annotations

from opentelemetry import metrics

meter = metrics.get_meter("contelligence.agent")

# ---------------------------------------------------------------------------
# Counters — discrete events
# ---------------------------------------------------------------------------

session_counter = meter.create_counter(
    "contelligence.sessions.created",
    description="Number of agent sessions created",
    unit="sessions",
)

tool_call_counter = meter.create_counter(
    "contelligence.tool_calls",
    description="Number of tool invocations",
    unit="calls",
)

error_counter = meter.create_counter(
    "contelligence.errors",
    description="Number of errors",
    unit="errors",
)

document_counter = meter.create_counter(
    "contelligence.documents.processed",
    description="Number of documents processed",
    unit="documents",
)

cache_hit_counter = meter.create_counter(
    "contelligence.cache.hits",
    description="Extraction cache hits",
    unit="hits",
)

cache_miss_counter = meter.create_counter(
    "contelligence.cache.misses",
    description="Extraction cache misses",
    unit="misses",
)

rate_limit_wait_counter = meter.create_counter(
    "contelligence.rate_limit.waits",
    description="Number of rate limit waits",
    unit="waits",
)

# ---------------------------------------------------------------------------
# Histograms — duration distributions
# ---------------------------------------------------------------------------

tool_duration_histogram = meter.create_histogram(
    "contelligence.tool_call.duration",
    description="Tool call execution duration",
    unit="ms",
)

session_duration_histogram = meter.create_histogram(
    "contelligence.session.duration",
    description="Session total duration",
    unit="s",
)

rate_limit_wait_histogram = meter.create_histogram(
    "contelligence.rate_limit.wait_duration",
    description="Time spent waiting for rate limit tokens",
    unit="ms",
)
