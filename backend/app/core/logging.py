"""Structured (JSON) application logging.

Every line carries: timestamp, level, module (logger name), message, and -
when inside a request - request_path and request_id. Extra fields passed via
``logger.info("...", extra={...})`` are included automatically.

Never pass passwords, API keys, secrets or full student records as log fields.
"""

import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import datetime, timezone

request_path_ctx: ContextVar[str | None] = ContextVar("request_path", default=None)
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else came from ``extra=``.
_STANDARD_RECORD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}
# Handled explicitly (and only when set) by JsonFormatter.
_CONTEXT_ATTRS = ("request_path", "request_id")


class RequestContextFilter(logging.Filter):
    """Attach request_path / request_id from the current request context."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_path", None) is None:
            record.request_path = request_path_ctx.get()
        if getattr(record, "request_id", None) is None:
            record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        for key in _CONTEXT_ATTRS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key not in payload and key not in _CONTEXT_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_context": {"()": RequestContextFilter}},
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                    "filters": ["request_context"],
                }
            },
            "root": {"level": level, "handlers": ["stdout"]},
            "loggers": {
                # Route uvicorn's own logs through the JSON handler.
                "uvicorn": {"handlers": [], "level": level, "propagate": True},
                "uvicorn.error": {"handlers": [], "level": level, "propagate": True},
                # Our middleware logs one line per request, so silence the duplicate.
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )
