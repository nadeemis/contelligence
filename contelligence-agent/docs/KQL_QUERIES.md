# HikmaForge KQL Queries & Alert Definitions

Reusable KQL queries for Application Insights monitoring and Azure Monitor alert rules.

---

## 1. Tool-Call Error Rate (5-min window)

```kql
customMetrics
| where name == "hikmaforge.tool_calls"
| where timestamp > ago(5m)
| extend tool = tostring(customDimensions.tool),
         status = tostring(customDimensions.status)
| summarize
    total = count(),
    errors = countif(status == "error")
    by tool, bin(timestamp, 1m)
| extend error_rate = todouble(errors) / todouble(total) * 100
| project timestamp, tool, total, errors, error_rate
| order by timestamp desc
```

**Alert rule:** Fire when `error_rate > 10%` for any tool over a 5-minute window.

---

## 2. Cache Hit Ratio

```kql
customMetrics
| where name in ("hikmaforge.cache.hits", "hikmaforge.cache.misses")
| where timestamp > ago(1h)
| summarize
    hits  = countif(name == "hikmaforge.cache.hits"),
    misses = countif(name == "hikmaforge.cache.misses")
    by bin(timestamp, 5m)
| extend hit_ratio = iff(hits + misses > 0,
                          todouble(hits) / todouble(hits + misses) * 100, 0.0)
| project timestamp, hits, misses, hit_ratio
| order by timestamp desc
```

---

## 3. Rate Limit Wait Duration (P95)

```kql
customMetrics
| where name == "hikmaforge.rate_limit.wait_duration"
| where timestamp > ago(1h)
| summarize
    p50 = percentile(value, 50),
    p95 = percentile(value, 95),
    p99 = percentile(value, 99)
    by bin(timestamp, 5m)
| order by timestamp desc
```

**Alert rule:** Fire when `p95 > 5000` ms (5 s) sustained over 10 min.

---

## 4. Session Duration Distribution

```kql
customMetrics
| where name == "hikmaforge.session.duration"
| where timestamp > ago(24h)
| summarize
    count_sessions = count(),
    p50 = percentile(value, 50),
    p95 = percentile(value, 95),
    max_val = max(value)
    by bin(timestamp, 1h)
| order by timestamp desc
```

---

## 5. Tool-Call Duration Heatmap

```kql
customMetrics
| where name == "hikmaforge.tool_call.duration"
| where timestamp > ago(6h)
| extend tool = tostring(customDimensions.tool)
| summarize
    p50 = percentile(value, 50),
    p95 = percentile(value, 95),
    calls = count()
    by tool, bin(timestamp, 15m)
| order by timestamp desc, tool asc
```

---

## 6. Error Breakdown by Type

```kql
customMetrics
| where name == "hikmaforge.errors"
| where timestamp > ago(24h)
| extend error_type = tostring(customDimensions.type)
| summarize count() by error_type, bin(timestamp, 1h)
| order by timestamp desc
```

**Alert rule:** Fire when total errors > 50 in a 5-minute window.

---

## 7. Active Sessions per Instance

```kql
customMetrics
| where name == "hikmaforge.sessions.created"
| where timestamp > ago(1h)
| extend instance = tostring(customDimensions["cloud.roleInstance"])
| summarize sessions = count() by instance, bin(timestamp, 5m)
| order by timestamp desc
```

---

## 8. Documents Processed

```kql
customMetrics
| where name == "hikmaforge.documents.processed"
| where timestamp > ago(24h)
| summarize docs = sum(value) by bin(timestamp, 1h)
| order by timestamp desc
```

---

## 9. Slow Requests (> 10 s)

```kql
requests
| where timestamp > ago(6h)
| where duration > 10000
| project timestamp, name, url, duration, resultCode,
          session_id = tostring(customDimensions.session_id),
          instance_id = tostring(customDimensions.instance_id)
| order by duration desc
```

---

## 10. Exceptions (Top 10)

```kql
exceptions
| where timestamp > ago(24h)
| summarize count() by type, outerMessage
| top 10 by count_
```

---

## Alert Definitions (Bicep parameters)

| Alert Name            | Signal                              | Condition                  | Frequency | Window |
|----------------------|---------------------------------------|---------------------------|-----------|--------|
| HighToolErrorRate    | `hikmaforge.tool_calls` error_rate   | > 10 %                    | 1 min     | 5 min  |
| HighP95RateWait      | `hikmaforge.rate_limit.wait_duration` p95 | > 5 000 ms           | 5 min     | 10 min |
| ErrorBurst           | `hikmaforge.errors` count            | > 50                      | 1 min     | 5 min  |
| LongRunningSession   | `hikmaforge.session.duration` p95    | > 3 600 s                 | 15 min    | 30 min |
| LowCacheHitRatio     | hikmaforge.cache hit_ratio           | < 20 %                    | 5 min     | 15 min |
