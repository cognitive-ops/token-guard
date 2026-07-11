#!/usr/bin/env python3
import logging
import os
import time

import requests
from prometheus_client import Gauge, start_http_server

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-tool-exporter")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9108"))
# Read timeout for the Loki query. The 30d count_over_time normally returns in
# ~30s (Loki splits it into parallel daily sub-queries); this bounds a stall so a
# poll can't hang forever, while staying well under Loki's own query_timeout.
QUERY_TIMEOUT = int(os.environ.get("QUERY_TIMEOUT_SECONDS", "180"))

# Grouped by tool_name only. Both consumers (web overview + usage-patterns) query
# `sum by (tool_name)(claude_tool_usage_count)`, and grouping by user_email as well
# exceeds Loki's 500-series-per-query cap (tools x users).
TOOL_USAGE = Gauge("claude_tool_usage_count", "Count of tool_result events", ["tool_name"])
EVENTS_SEEN = Gauge("claude_tool_usage_events_total", "Total tool_result events processed")
LAST_SUCCESS = Gauge("claude_tool_exporter_last_success_timestamp", "Unix ts of last good poll")
SCRAPE_ERRORS = Gauge("claude_tool_exporter_errors", "1 if last poll failed, else 0")


def poll_loki():
    try:
        log.info(f"Polling Loki for {LOOKBACK_DAYS}d of tool_result events...")

        # One aggregated metric query instead of paging through raw log lines.
        # tool_name is structured metadata, so count_over_time groups by it directly.
        query = (
            "sum by (tool_name) "
            f'(count_over_time({{service_name="claude-code"}} | event_name="tool_result" [{LOOKBACK_DAYS}d]))'
        )
        resp = requests.get(
            f"{LOKI_URL}/loki/api/v1/query",
            params={"query": query},
            timeout=(10, QUERY_TIMEOUT),
        )
        resp.raise_for_status()
        result = resp.json().get("data", {}).get("result", [])

        counts = {}
        total_events = 0
        for series in result:
            tool_name = series.get("metric", {}).get("tool_name")
            if not tool_name:
                continue
            count = int(float(series.get("value", [0, "0"])[1]))
            counts[tool_name] = count
            total_events += count

        TOOL_USAGE.clear()
        for tool_name, count in counts.items():
            TOOL_USAGE.labels(tool_name=tool_name).set(count)

        EVENTS_SEEN.set(total_events)
        LAST_SUCCESS.set_to_current_time()
        SCRAPE_ERRORS.set(0)
        log.info(f"Poll successful: {total_events} events, {len(counts)} tools")
    except Exception as e:
        log.error(f"Poll failed: {e}")
        SCRAPE_ERRORS.set(1)


def main():
    start_http_server(LISTEN_PORT)
    log.info(f"Listening on port {LISTEN_PORT}")
    poll_loki()
    while True:
        time.sleep(POLL_INTERVAL)
        poll_loki()


if __name__ == "__main__":
    main()
