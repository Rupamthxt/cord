"""Structured logging configuration for Notion crawler."""

import logging
import json
from datetime import datetime
from typing import Any, Dict

class StructuredLogger:
    """Structured logging for production monitoring."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _log_structured(self, level: int, message: str, **kwargs):
        """Log with structured metadata."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            **kwargs
        }
        self.logger.log(level, json.dumps(log_data))
    
    def info(self, message: str, **metadata):
        """Log info with metadata."""
        self._log_structured(logging.INFO, message, **metadata)
    
    def warning(self, message: str, **metadata):
        """Log warning with metadata."""
        self._log_structured(logging.WARNING, message, **metadata)
    
    def error(self, message: str, **metadata):
        """Log error with metadata."""
        self._log_structured(logging.ERROR, message, **metadata)
    
    def debug(self, message: str, **metadata):
        """Log debug with metadata."""
        self._log_structured(logging.DEBUG, message, **metadata)


def get_logger(name: str) -> StructuredLogger:
    """Get a configured structured logger."""
    return StructuredLogger(name)
