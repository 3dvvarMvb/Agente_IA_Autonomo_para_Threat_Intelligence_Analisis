"""Structured logging configuration with secret redaction and correlation IDs."""

import logging
import re
import sys

# Regex patterns for detecting and redacting common secret tokens in log messages
SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key[\s:=]+)([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(token[\s:=]+)([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(secret[\s:=]+)([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(x-apikey[\s:=]+)([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
]


class SecretRedactingFilter(logging.Filter):
    """Filter that masks API keys, bearer tokens and passwords in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self.redact(v) if isinstance(v, str) else v) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    (self.redact(arg) if isinstance(arg, str) else arg) for arg in record.args
                )
        return True

    @staticmethod
    def redact(message: str) -> str:
        for pattern in SECRET_PATTERNS:
            message = pattern.sub(r"\1[REDACTED]", message)
        return message


def setup_logging(
    level: str = "INFO",
    log_format: str | None = None,
) -> None:
    """Configure the root logger with redaction filter and unified formatting."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    default_format = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt=log_format or default_format, datefmt="%Y-%m-%d %H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SecretRedactingFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with redaction filter attached."""
    logger = logging.getLogger(name)
    logger.addFilter(SecretRedactingFilter())
    return logger
