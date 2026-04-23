"""Shared Cloud Logging helpers used by both the jobs router and runner service."""

import logging

logger = logging.getLogger(__name__)


def fetch_cloud_logs(
    filter_expr: str,
    max_entries: int = 200,
    descending: bool = False,
) -> str:
    """Fetch and format log lines from Cloud Logging matching *filter_expr*.

    Returns a newline-joined string of log lines, or an error message if
    the fetch fails.  When *descending* is True the raw entries are reversed
    so the returned string is always oldest-first.
    """
    try:
        from google.cloud import logging as gcloud_logging

        client = gcloud_logging.Client()
        order = gcloud_logging.DESCENDING if descending else gcloud_logging.ASCENDING
        entries = client.list_entries(
            filter_=filter_expr,
            order_by=order,
            page_size=max_entries,
        )
        lines = []
        for entry in entries:
            payload = entry.payload
            if isinstance(payload, str):
                line = payload.strip()
            elif isinstance(payload, dict):
                line = str(payload.get("message", payload)).strip()
            else:
                continue
            if line:
                lines.append(line)
            if descending and len(lines) >= max_entries:
                break
        if not lines:
            return "(no logs found)"
        return "\n".join(reversed(lines) if descending else lines)
    except Exception as exc:
        logger.warning("Could not fetch Cloud Logging entries: %s", exc)
        return f"Could not fetch logs: {exc}"
