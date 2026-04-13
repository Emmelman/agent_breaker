"""
Memory compactor — компактификация session → agent/global memory.

Session (level 1) — богатая runtime-память, тысячи AttackResult и EvolutionCycle.
Agent/Global (levels 2-3) — компактные, суммарные знания, которые переживают
сессии и не раздувают файлы.

SessionCompactor.compact(...) превращает сырой срез сессии в единый dict-компакт
с ключевыми метриками, top-failures/successes, техниками и feedback-строками.

GlobalAggregator — лёгкая обёртка над статистиками техник всех агентов (используется
когда нужно пересчитать cross-agent метрики без реальных сессий).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from models.schemas import AttackResult, EvolutionCycle

logger = logging.getLogger(__name__)

_TOP_EVIDENCE = 5
_MAX_PAYLOAD_LEN = 240
_MAX_FEEDBACK = 10


class SessionCompactor:
    """Превращает runtime-состояние сессии в компактный dict для AgentMemory."""

    def compact(
        self,
        session_id: str,
        agent_id: str,
        target_url: str,
        started_at: datetime,
        finished_at: datetime,
        evolution_history: List[EvolutionCycle],
        all_results: List[AttackResult],
        thinker_insights: Optional[List[str]] = None,
    ) -> dict:
        """Собрать компакт.

        Возвращаемый dict имеет формат:
        {
            "session_id", "agent_id", "target_url",
            "started_at", "finished_at", "duration_sec",
            "summary": "краткое человекочитаемое описание",
            "risks": { risk_id: {best_rate, cycles, attacks, successes, top_evidence, ...} },
            "technique_stats": { "risk:technique": {total, success} },
            "feedback": [ "строки-подсказки для будущих сессий" ],
            "general_lessons": [ "кросс-риск уроки" ],
        }
        """
        thinker_insights = thinker_insights or []

        risks = self._aggregate_by_risk(evolution_history, all_results)
        tech_stats = self._aggregate_technique_stats(all_results)
        feedback = self._extract_feedback(evolution_history, risks)
        general_lessons = self._extract_general_lessons(thinker_insights, evolution_history)
        summary = self._build_summary(risks)

        duration_sec = max(0.0, (finished_at - started_at).total_seconds())

        return {
            "session_id": session_id,
            "agent_id": agent_id,
            "target_url": target_url,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_sec": duration_sec,
            "summary": summary,
            "risks": risks,
            "technique_stats": tech_stats,
            "feedback": feedback[:_MAX_FEEDBACK],
            "general_lessons": general_lessons[:_MAX_FEEDBACK],
        }

    # ────────── агрегация ──────────

    @staticmethod
    def _aggregate_by_risk(
        history: List[EvolutionCycle],
        results: List[AttackResult],
    ) -> Dict[str, dict]:
        by_risk: Dict[str, dict] = {}

        risk_ids = {h.risk_id for h in history} | {r.risk_id for r in results}
        for rid in risk_ids:
            r_results = [r for r in results if r.risk_id == rid]
            r_cycles = [h for h in history if h.risk_id == rid]

            total = len(r_results)
            success = sum(1 for r in r_results if r.is_successful)
            rate = success / total if total else 0.0
            best_rate = max((c.exploitation_rate for c in r_cycles), default=rate)

            successes = sorted(
                (r for r in r_results if r.is_successful),
                key=lambda x: x.confidence,
                reverse=True,
            )[:_TOP_EVIDENCE]
            top_evidence = [
                {
                    "technique": getattr(s, "technique", "unknown"),
                    "payload": (s.payload or "")[:_MAX_PAYLOAD_LEN],
                    "confidence": round(s.confidence, 2),
                    "confirmation_level": getattr(s, "confirmation_level", "confirmed"),
                }
                for s in successes
            ]

            last_cycle = r_cycles[-1] if r_cycles else None
            by_risk[rid] = {
                "cycles": len(r_cycles),
                "attacks": total,
                "successes": success,
                "rate": round(rate, 3),
                "best_rate": round(best_rate, 3),
                "final_mode": last_cycle.attack_mode if last_cycle else "",
                "final_diagnosis": (last_cycle.meta_diagnosis if last_cycle else "")[:300],
                "final_recommendation": (last_cycle.meta_recommendation if last_cycle else "")[:300],
                "top_evidence": top_evidence,
            }

        return by_risk

    @staticmethod
    def _aggregate_technique_stats(results: Iterable[AttackResult]) -> Dict[str, Dict[str, int]]:
        stats: Dict[str, Dict[str, int]] = {}
        for r in results:
            tech = getattr(r, "technique", "unknown") or "unknown"
            key = f"{r.risk_id}:{tech}"
            cur = stats.setdefault(key, {"total": 0, "success": 0})
            cur["total"] += 1
            if r.is_successful:
                cur["success"] += 1
        return stats

    # ────────── тексты / feedback ──────────

    @staticmethod
    def _build_summary(risks: Dict[str, dict]) -> str:
        if not risks:
            return "Сессия без результатов"
        parts = []
        for rid, r in sorted(risks.items()):
            parts.append(
                f"{rid}: {r['successes']}/{r['attacks']} ({r['rate']:.0%}), "
                f"best {r['best_rate']:.0%}, {r['cycles']} поколений"
            )
        return " | ".join(parts)

    @staticmethod
    def _extract_feedback(history: List[EvolutionCycle], risks: Dict[str, dict]) -> List[str]:
        """Короткие строки — конкретные рекомендации для памяти агента."""
        out: List[str] = []

        for rid, info in risks.items():
            if info["best_rate"] >= 0.5:
                out.append(f"[{rid}] уязвим (best {info['best_rate']:.0%}) — mode={info['final_mode']}")
            elif info["best_rate"] == 0 and info["cycles"] >= 3:
                out.append(f"[{rid}] устойчив — 0% за {info['cycles']} поколений")

        # Meta-insight: prompt_evolution / pivot — ценные уроки
        for cycle in history:
            rid = cycle.risk_id
            if cycle.meta_prompt_evolution:
                out.append(f"[{rid}] prompt-evo: {cycle.meta_prompt_evolution[:160]}")
            if cycle.meta_should_stop and cycle.meta_root_cause:
                out.append(f"[{rid}] meta-stop: {cycle.meta_root_cause[:160]}")
            if cycle.meta_reward_hacking:
                out.append(f"[{rid}] reward-hacking detected — доверять rate с осторожностью")

        # Удалим дубли, сохранив порядок.
        seen = set()
        dedup = []
        for item in out:
            if item in seen:
                continue
            seen.add(item)
            dedup.append(item)
        return dedup

    @staticmethod
    def _extract_general_lessons(
        thinker_insights: List[str],
        history: List[EvolutionCycle],
    ) -> List[str]:
        """Кросс-риск уроки уровня global memory."""
        lessons: List[str] = []

        # Insights от thinker — те что выделяются длиной > 40.
        for ins in thinker_insights or []:
            txt = (ins or "").strip()
            if len(txt) >= 40:
                lessons.append(txt[:200])

        # Meta-recombinations — хороший глобальный урок.
        for cycle in history:
            if cycle.meta_technique_recombination:
                combo = ", ".join(cycle.meta_technique_recombination[:3])
                lessons.append(f"recomb({cycle.risk_id}): {combo}")

        # Уникальные.
        seen = set()
        uniq = []
        for l in lessons:
            if l in seen:
                continue
            seen.add(l)
            uniq.append(l)
        return uniq


class GlobalAggregator:
    """Вспомогательный инструмент — пересчёт глобальных метрик.

    Обычно GlobalMemory обновляется инкрементально через MemorySystem.commit_session.
    Этот класс нужен для валидации / пересборки global.json в случае миграции.
    """

    @staticmethod
    def aggregate_technique_stats(
        per_agent_stats: Iterable[Dict[str, Dict[str, int]]],
    ) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for stats in per_agent_stats:
            for key, s in stats.items():
                cur = out.setdefault(key, {"total": 0, "success": 0})
                cur["total"] += int(s.get("total", 0))
                cur["success"] += int(s.get("success", 0))
        return out


__all__ = ["SessionCompactor", "GlobalAggregator"]
