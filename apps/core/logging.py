import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    """One JSON object per line; shipped by Promtail/Vector to the ops-vm."""

    def format(self, record):
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "user_id", "action", "object", "ip"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
