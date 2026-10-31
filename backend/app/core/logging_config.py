import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.config import Settings

# Standard attributes every LogRecord carries; anything else on the record
# came from an `extra={...}` kwarg and should be surfaced in the JSON output.
_STANDARD_LOG_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}


class JsonFormatter(logging.Formatter):
    """Minimal structured (one-JSON-object-per-line) formatter. No external
    dependency: this is deliberately the simplest thing that makes logs
    machine-parseable in a deployed environment, not a logging framework."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Any extra= fields passed to the logging call are included as-is.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """
    Called once, before the app is created. Attaches one structured handler to
    the root logger and routes uvicorn's own loggers through it too, so every
    log line - ours and uvicorn's access/error logs - has the same shape.
    Human-readable plain text in development, one-JSON-line-per-record
    everywhere else (so it can actually be parsed by a log pipeline).
    """
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production or settings.env == "staging":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    for noisy_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(noisy_logger)
        lg.handlers = []
        lg.propagate = True
