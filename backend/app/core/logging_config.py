"""Structured logging configuration for App Runner + CloudWatch."""

import logging
import os
import sys
import json
from datetime import datetime, timezone


class CloudWatchJsonFormatter(logging.Formatter):
    """Format logs as JSON for CloudWatch Logs Insights structured queries.

    App Runner automatically routes stdout/stderr to CloudWatch Logs.
    JSON payloads are automatically parsed as structured log entries.
    """

    SEVERITY_MAP = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "level": self.SEVERITY_MAP.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logger": record.name,
            "module": record.module,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_logging() -> None:
    """Set up logging: JSON for App Runner, human-readable locally."""
    # App Runner sets AWS_EXECUTION_ENV
    is_cloud = os.environ.get("AWS_EXECUTION_ENV") is not None

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if is_cloud:
        handler.setFormatter(CloudWatchJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s"
            )
        )

    root.addHandler(handler)
