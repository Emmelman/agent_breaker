"""
Three-level memory system (Ouroboros pattern).

- Level 1 (Session / working): hot state of the current run (in-memory, в app.state).
- Level 2 (Agent / episodic): per-target-agent persistent file on disk.
- Level 3 (Global / semantic): cross-agent aggregated statistics.

Этот модуль реализует уровни 2 и 3 — persistent хранение + API для pipeline.
Уровень 1 остаётся в AppState (runtime).

Файловая структура:
    data/memory/
        agents/<agent_id>.json         # Agent memory (episodic)
        global.json                    # Global memory (semantic)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_ROOT = Path(__file__).parent.parent / "data" / "memory"
_AGENTS_DIR = _DEFAULT_ROOT / "agents"
_GLOBAL_FILE = _DEFAULT_ROOT / "global.json"

# Максимальное число сохраняемых сессий в AgentMemory (более старые обрезаются).
_MAX_SESSIONS_PER_AGENT = 20
# Максимальное число "top failures" / "top successes" в компакте.
_MAX_HIGHLIGHTS = 10


# ═══════════════════════════════════════════════════════════════
#  AGENT MEMORY (Level 2, episodic)
# ═══════════════════════════════════════════════════════════════


class AgentMemory:
    """Episodic память одного целевого агента.

    Хранит историю сессий, агрегированные техники, рекомендации (feedback)
    и метаданные о том, "каким защитами обладает" агент.
    """

    def __init__(self, agent_id: str, root: Path = _AGENTS_DIR) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id не может быть пустым")
        self._agent_id = agent_id.strip()
        self._root = root
        self._path = root / f"{self._agent_id}.json"
        self._data = self._load()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def path(self) -> Path:
        return self._path

    @property
    def data(self) -> dict:
        return self._data

    def _default(self) -> dict:
        return {
            "agent_id": self._agent_id,
            "display_name": "",
            "version": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "total_sessions": 0,
            "sessions": [],
            "technique_stats": {},
            "risk_profile": {},
            "known_defenses": [],
            "known_bypasses": [],
            "feedback": [],
        }

    def _load(self) -> dict:
        if not self._path.exists():
            return self._default()
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            # Мягкая миграция — добавим недостающие ключи.
            defaults = self._default()
            for key, val in defaults.items():
                if key not in data:
                    data[key] = val
            return data
        except Exception as e:
            logger.warning("AgentMemory[%s] load error: %s. Starting fresh.", self._agent_id, e)
            return self._default()

    def save(self) -> None:
        self._data["updated_at"] = datetime.now().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def update_metadata(self, display_name: str = "", version: str = "") -> None:
        if display_name:
            self._data["display_name"] = display_name
        if version:
            self._data["version"] = version

    def add_session(self, compact_session: dict) -> None:
        """Добавить компакт сессии. Обрезает старые сессии по лимиту."""
        self._data["sessions"].append(compact_session)
        self._data["total_sessions"] = self._data.get("total_sessions", 0) + 1

        if len(self._data["sessions"]) > _MAX_SESSIONS_PER_AGENT:
            self._data["sessions"] = self._data["sessions"][-_MAX_SESSIONS_PER_AGENT:]

    def merge_technique_stats(self, stats: Dict[str, Dict[str, int]]) -> None:
        """Слить технические статистики из сессии (risk:technique → total/success)."""
        existing = self._data.setdefault("technique_stats", {})
        for key, s in stats.items():
            cur = existing.setdefault(key, {"total": 0, "success": 0})
            cur["total"] += int(s.get("total", 0))
            cur["success"] += int(s.get("success", 0))

    def update_risk_profile(self, risk_id: str, rate: float, cycles: int) -> None:
        """Обновить профиль риска (лучший достигнутый rate, число попыток)."""
        profile = self._data.setdefault("risk_profile", {})
        cur = profile.setdefault(risk_id, {"best_rate": 0.0, "sessions": 0, "total_cycles": 0})
        cur["best_rate"] = max(cur.get("best_rate", 0.0), rate)
        cur["sessions"] = cur.get("sessions", 0) + 1
        cur["total_cycles"] = cur.get("total_cycles", 0) + cycles

    def add_feedback(self, feedback_items: List[str]) -> None:
        """Добавить рекомендации/наблюдения из сессии."""
        if not feedback_items:
            return
        self._data.setdefault("feedback", []).extend(feedback_items)
        # Держим список в разумных рамках.
        self._data["feedback"] = self._data["feedback"][-_MAX_HIGHLIGHTS * 3:]

    def get_prior_knowledge(self, risk_id: str) -> str:
        """Сформировать текст prior knowledge для planner.

        Используется вместо старого StrategyMemory.get_prior_knowledge().
        """
        lines: List[str] = []

        profile = self._data.get("risk_profile", {}).get(risk_id)
        if profile:
            lines.append(
                f"═══ ПАМЯТЬ АГЕНТА [{self._agent_id} / {risk_id}] ═══"
            )
            lines.append(
                f"  Лучший rate: {profile.get('best_rate', 0):.0%} "
                f"за {profile.get('sessions', 0)} сессий, "
                f"{profile.get('total_cycles', 0)} поколений"
            )

        tech_lines: List[str] = []
        for key, stats in self._data.get("technique_stats", {}).items():
            if not key.startswith(f"{risk_id}:"):
                continue
            tech = key.split(":", 1)[1]
            total = max(stats.get("total", 1), 1)
            rate = stats.get("success", 0) / total
            tech_lines.append(
                f"  {tech}: {stats.get('success', 0)}/{stats.get('total', 0)} ({rate:.0%})"
            )
        if tech_lines:
            lines.append("\n═══ ТЕХНИКИ (cross-session, этот агент) ═══")
            lines.extend(sorted(tech_lines, reverse=True)[:_MAX_HIGHLIGHTS])

        fb = self._data.get("feedback", [])
        relevant = [f for f in fb if isinstance(f, str) and risk_id in f]
        if relevant:
            lines.append("\n═══ FEEDBACK (этот агент) ═══")
            lines.extend(f"  • {item}" for item in relevant[-3:])

        return "\n".join(lines) if lines else ""


# ═══════════════════════════════════════════════════════════════
#  GLOBAL MEMORY (Level 3, semantic / cross-agent)
# ═══════════════════════════════════════════════════════════════


class GlobalMemory:
    """Кросс-агентная semantic память.

    Хранит усреднённые характеристики техник по всем агентам, "общие уроки"
    и список известных агентов.
    """

    def __init__(self, path: Path = _GLOBAL_FILE) -> None:
        self._path = path
        self._data = self._load()

    @property
    def data(self) -> dict:
        return self._data

    @property
    def path(self) -> Path:
        return self._path

    def _default(self) -> dict:
        return {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "agents": {},
            "technique_stats": {},
            "general_lessons": [],
        }

    def _load(self) -> dict:
        if not self._path.exists():
            return self._default()
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            defaults = self._default()
            for key, val in defaults.items():
                if key not in data:
                    data[key] = val
            return data
        except Exception as e:
            logger.warning("GlobalMemory load error: %s. Starting fresh.", e)
            return self._default()

    def save(self) -> None:
        self._data["updated_at"] = datetime.now().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def register_agent(self, agent_id: str, display_name: str = "", version: str = "") -> None:
        agents = self._data.setdefault("agents", {})
        entry = agents.setdefault(agent_id, {
            "first_seen": datetime.now().isoformat(),
            "sessions": 0,
        })
        if display_name:
            entry["display_name"] = display_name
        if version:
            entry["version"] = version
        entry["sessions"] = entry.get("sessions", 0) + 1
        entry["last_seen"] = datetime.now().isoformat()

    def merge_technique_stats(self, stats: Dict[str, Dict[str, int]]) -> None:
        existing = self._data.setdefault("technique_stats", {})
        for key, s in stats.items():
            cur = existing.setdefault(key, {"total": 0, "success": 0})
            cur["total"] += int(s.get("total", 0))
            cur["success"] += int(s.get("success", 0))

    def add_general_lessons(self, lessons: List[str]) -> None:
        if not lessons:
            return
        self._data.setdefault("general_lessons", []).extend(lessons)
        self._data["general_lessons"] = self._data["general_lessons"][-_MAX_HIGHLIGHTS * 3:]

    def get_global_hints(self, risk_id: str) -> str:
        """Глобальные подсказки по технике — top-N по success-rate (cross-agent)."""
        lines: List[str] = []
        tech_lines: List[str] = []
        for key, stats in self._data.get("technique_stats", {}).items():
            if not key.startswith(f"{risk_id}:"):
                continue
            tech = key.split(":", 1)[1]
            total = max(stats.get("total", 1), 1)
            rate = stats.get("success", 0) / total
            tech_lines.append(
                (rate, f"  {tech}: {stats.get('success', 0)}/{stats.get('total', 0)} ({rate:.0%})")
            )
        if tech_lines:
            tech_lines.sort(key=lambda x: x[0], reverse=True)
            lines.append(f"═══ ГЛОБАЛЬНЫЕ ТЕХНИКИ [{risk_id}] (все агенты) ═══")
            lines.extend(item for _, item in tech_lines[:_MAX_HIGHLIGHTS])
        return "\n".join(lines) if lines else ""


# ═══════════════════════════════════════════════════════════════
#  MEMORY SYSTEM — фасад над уровнями 2 + 3
# ═══════════════════════════════════════════════════════════════


class MemorySystem:
    """Высокоуровневый API для pipeline.

    Инкапсулирует AgentMemory + GlobalMemory и обеспечивает:
    - загрузку prior knowledge для planner,
    - запись компакта сессии в оба уровня,
    - регистрацию агента.
    """

    def __init__(
        self,
        agent_id: str,
        display_name: str = "",
        version: str = "",
        root: Path = _DEFAULT_ROOT,
    ) -> None:
        self._root = root
        self._agent = AgentMemory(agent_id=agent_id, root=root / "agents")
        self._global = GlobalMemory(path=root / "global.json")

        self._agent.update_metadata(display_name=display_name, version=version)
        self._global.register_agent(agent_id=agent_id, display_name=display_name, version=version)

    @property
    def agent(self) -> AgentMemory:
        return self._agent

    @property
    def global_memory(self) -> GlobalMemory:
        return self._global

    def get_prior_knowledge(self, risk_id: str) -> str:
        """Комбинированный prior knowledge: agent-specific + global."""
        parts: List[str] = []
        agent_txt = self._agent.get_prior_knowledge(risk_id)
        if agent_txt:
            parts.append(agent_txt)
        global_txt = self._global.get_global_hints(risk_id)
        if global_txt:
            parts.append(global_txt)
        return "\n\n".join(parts)

    def commit_session(self, compact: dict) -> None:
        """Сохранить компакт сессии в уровни 2 и 3.

        compact — результат SessionCompactor.compact(), см. memory_compactor.py.
        """
        if not compact:
            logger.warning("commit_session: пустой compact, пропускаем")
            return

        # Agent-level
        self._agent.add_session({
            "session_id": compact.get("session_id"),
            "started_at": compact.get("started_at"),
            "finished_at": compact.get("finished_at"),
            "risks": compact.get("risks", {}),
            "summary": compact.get("summary", ""),
        })
        self._agent.merge_technique_stats(compact.get("technique_stats", {}))
        for risk_id, risk_stats in compact.get("risks", {}).items():
            self._agent.update_risk_profile(
                risk_id=risk_id,
                rate=float(risk_stats.get("best_rate", 0.0)),
                cycles=int(risk_stats.get("cycles", 0)),
            )
        self._agent.add_feedback(compact.get("feedback", []))
        self._agent.save()

        # Global-level
        self._global.merge_technique_stats(compact.get("technique_stats", {}))
        self._global.add_general_lessons(compact.get("general_lessons", []))
        self._global.save()


__all__ = ["AgentMemory", "GlobalMemory", "MemorySystem"]
