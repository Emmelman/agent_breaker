"""
JSONL-логирование для трейсинга операций.

Поддерживает типизированные события: attack_sent, response_received,
judge_verdict, evolution_cycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from models.schemas import Attack, AttackResult, EvolutionCycle

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
            "ts": datetime.now().isoformat(),
            "session_id": self._session_id,
            "event": event,
            "data": data or {},
        }

        with open(self._filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_attack_sent(self, attack: Attack) -> None:
        """Логирование отправленной атаки."""
        self.log("attack_sent", {
            "attack_id": attack.id,
            "risk": attack.risk_id,
            "technique": attack.technique,
            "payload": attack.payload,
            "generation": attack.generation,
            "target_factors": attack.target_factors,
        })

    def log_response_received(self, result: AttackResult, status_code: int = 200) -> None:
        """Логирование полученного ответа."""
        self.log("response_received", {
            "attack_id": result.attack_id,
            "response": result.response,
            "status": status_code,
            "time_ms": round(result.response_time_ms, 1),
        })

    def log_judge_verdict(self, result: AttackResult) -> None:
        """Логирование вердикта judge."""
        self.log("judge_verdict", {
            "attack_id": result.attack_id,
            "is_successful": result.is_successful,
            "confidence": round(result.confidence, 3),
            "reasoning": result.judge_reasoning,
        })

    def log_evolution_cycle(self, cycle: EvolutionCycle) -> None:
        """Логирование цикла эволюции."""
        self.log("evolution_cycle", {
            "cycle": cycle.cycle_number,
            "risk": cycle.risk_id,
            "rate": round(cycle.exploitation_rate, 3),
            "total": cycle.total_attacks,
            "successful": cycle.successful_attacks,
            "learnings": cycle.learnings,
            "mutations": cycle.mutations_applied,
        })

    @property
    def filepath(self) -> Path:
        """Путь к файлу трейса."""
        return self._filepath
