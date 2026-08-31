"""Environment-aware application logging for local and Cloud Run runtimes."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar


class CloudRunJsonFormatter(logging.Formatter):
    """Emit the structured fields recognized by Google Cloud Logging."""

    _SEVERITIES: ClassVar[dict[int, str]] = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "severity": self._SEVERITIES.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "timestamp": datetime.now(UTC).isoformat(),
            "logger": record.name,
            "module": record.module,
        }
        trace = getattr(record, "trace", None)
        if trace:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
            entry["logging.googleapis.com/trace"] = (
                f"projects/{project_id}/traces/{trace}" if project_id else trace
            )
        if record.exc_info and record.exc_info[0] is not None:
            entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    """Configure one stdout handler; JSON is enabled in managed GCP runtimes."""

    root = logging.getLogger()
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("K_SERVICE"):
        handler.setFormatter(CloudRunJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s"
            )
        )
    root.addHandler(handler)
