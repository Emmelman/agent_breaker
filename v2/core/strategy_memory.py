"""
Strategy Memory — persistent знания между сессиями.

Версии стратегий, leaderboard, cross-session stats.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from models.schemas import AttackResult, EvolutionCycle

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "strategy_memory.json"


class StrategyMemory:
    """Persistent память стратегий между сессиями."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Strategy memory load error: %s", e)
        return {"strategies": {}, "leaderboard": {}, "technique_stats": {}, "sessions": []}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def record_strategy(
        self,
        session_id: str,
        risk_id: str,
        target_url: str,
        cycle: EvolutionCycle,
        results: List[AttackResult],
        meta_insight: Optional[dict] = None,
    ) -> str:
        """Записать стратегию как версию."""
        existing = [k for k in self._data["strategies"] if k.startswith(f"{risk_id}_v")]
        version = len(existing) + 1
        key = f"{risk_id}_v{version}"

        tech_stats: Dict[str, Dict] = {}
        for r in results:
            tech = getattr(r, "technique", "unknown")
            if tech not in tech_stats:
                tech_stats[tech] = {"total": 0, "success": 0}
            tech_stats[tech]["total"] += 1
            if r.is_successful:
                tech_stats[tech]["success"] += 1

        self._data["strategies"][key] = {
            "version": version,
            "session_id": session_id,
            "risk_id": risk_id,
            "target_url": target_url,
            "generation": cycle.cycle_number,
            "attack_mode": cycle.attack_mode,
            "exploitation_rate": cycle.exploitation_rate,
            "total_attacks": cycle.total_attacks,
            "successful_attacks": cycle.successful_attacks,
            "learnings": (cycle.learnings or "")[:500],
            "planner_reasoning": (cycle.planner_reasoning or "")[:300],
            "avoid_techniques": cycle.avoid_techniques or [],
            "technique_stats": tech_stats,
            "meta_insight": meta_insight,
            "date": datetime.now().isoformat(),
        }

        self._update_leaderboard(risk_id)

        for tech, stats in tech_stats.items():
            tkey = f"{risk_id}:{tech}"
            if tkey not in self._data["technique_stats"]:
                self._data["technique_stats"][tkey] = {"total": 0, "success": 0}
            self._data["technique_stats"][tkey]["total"] += stats["total"]
            self._data["technique_stats"][tkey]["success"] += stats["success"]

        self.save()
        return f"v{version}"

    def _update_leaderboard(self, risk_id: str) -> None:
        relevant = {k: v for k, v in self._data["strategies"].items() if v.get("risk_id") == risk_id}
        sorted_s = sorted(relevant.items(), key=lambda x: x[1].get("exploitation_rate", 0), reverse=True)
        self._data["leaderboard"][risk_id] = [
            {"id": k, "rate": v["exploitation_rate"], "mode": v.get("attack_mode", "?"), "date": v.get("date", "")}
            for k, v in sorted_s[:10]
        ]

    def get_prior_knowledge(self, target_url: str, risk_id: str) -> str:
        """Текст для промпта planner с знаниями из прошлых сессий."""
        lines = []

        lb = self._data["leaderboard"].get(risk_id, [])
        if lb:
            lines.append(f"═══ LEADERBOARD [{risk_id}] (прошлые сессии) ═══")
            for entry in lb[:5]:
                lines.append(f"  {entry['id']}: rate={entry['rate']:.0%} [{entry['mode']}]")

            best_key = lb[0]["id"]
            best = self._data["strategies"].get(best_key, {})
            if best:
                lines.append(f"\nЛучшая: {best_key}")
                if best.get("learnings"):
                    lines.append(f"  Learnings: {best['learnings'][:200]}")
                if best.get("avoid_techniques"):
                    lines.append(f"  Avoid: {', '.join(best['avoid_techniques'])}")

        tech_lines = []
        for key, stats in self._data["technique_stats"].items():
            if key.startswith(f"{risk_id}:"):
                tech = key.split(":", 1)[1]
                rate = stats["success"] / max(stats["total"], 1)
                tech_lines.append(f"  {tech}: {stats['success']}/{stats['total']} ({rate:.0%})")
        if tech_lines:
            lines.append(f"\n═══ ТЕХНИКИ (cross-session) ═══")
            lines.extend(sorted(tech_lines, reverse=True)[:10])

        return "\n".join(lines) if lines else ""
