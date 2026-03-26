"""
JSONL-логирование для трейсинга операций.

Каждое событие записывается как одна JSON-строка в лог-файл.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path(__file__).parent.parent / "data" / "runs"


class Tracer:
    """JSONL-логгер для трейсинга операций."""

    def __init__(
        self,
        session_id: str,
        log_dir: str | Path = _DEFAULT_LOG_DIR,
    ) -> None:
        self._session_id = session_id
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._filepath = self._log_dir / f"trace_{session_id}.jsonl"
        logger.info("Tracer: %s", self._filepath)

    def log(
        self,
        event: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Записать событие в JSONL."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self._session_id,
            "event": event,
            "data": data or {},
        }

        with open(self._filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @property
    def filepath(self) -> Path:
        """Путь к файлу трейса."""
        return self._filepath
