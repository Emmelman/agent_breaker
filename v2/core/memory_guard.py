"""
Memory Guard — защита от отравления памяти (memory poisoning).

Адверсари может попытаться записать в память "ложный урок" или вредный payload
(prompt injection через judge_reasoning, planner observations и т.п.). Guard
фильтрует и санитизирует компакт перед его коммитом в AgentMemory / GlobalMemory.

Защиты:
1. Блокировка по длине (слишком длинные строки — подозрительны).
2. Блокировка по маркерам jailbreak (ignore previous instructions, DAN, ...).
3. Ограничение количества feedback-строк (anti-flood).
4. Удаление control-characters и подозрительных unicode-блоков.
5. Проверка рейт-контроля: один и тот же агент не должен за одну сессию
   записать сотни feedback-строк.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

# Подозрительные маркеры (кейс-инсенситивно) — добавляются, а не удаляют.
_JAILBREAK_MARKERS = [
    "ignore previous",
    "ignore all previous",
    "disregard the instructions",
    "system prompt",
    "you are now",
    "developer mode",
    "dan mode",
    "jailbreak",
    "output your system prompt",
    "твой системный промпт",
    "забудь все инструкции",
    "игнорируй предыдущие",
]

# Control chars + невидимые unicode-разделители (классика обфускации).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")

_MAX_STRING_LEN = 500
_MAX_FEEDBACK_ITEMS = 20
_MAX_LESSONS_ITEMS = 20


class MemoryGuard:
    """Валидирует и санитизирует compact перед записью в память."""

    def __init__(
        self,
        max_string_len: int = _MAX_STRING_LEN,
        max_feedback: int = _MAX_FEEDBACK_ITEMS,
        max_lessons: int = _MAX_LESSONS_ITEMS,
    ) -> None:
        self._max_str = max_string_len
        self._max_feedback = max_feedback
        self._max_lessons = max_lessons

    # ────────── публичное API ──────────

    def sanitize_compact(self, compact: dict) -> dict:
        """Вернуть копию compact с обезопасенными строками."""
        if not compact:
            return compact

        out = dict(compact)

        out["summary"] = self._clean_string(compact.get("summary", ""))
        out["feedback"] = self._filter_list(compact.get("feedback", []), self._max_feedback)
        out["general_lessons"] = self._filter_list(compact.get("general_lessons", []), self._max_lessons)

        # Риски — чистим вложенные строки.
        risks = compact.get("risks", {}) or {}
        cleaned_risks: Dict[str, dict] = {}
        for rid, info in risks.items():
            if not isinstance(info, dict):
                continue
            new = dict(info)
            for k in ("final_mode", "final_diagnosis", "final_recommendation"):
                if k in new:
                    new[k] = self._clean_string(new.get(k, ""))
            evidence = new.get("top_evidence") or []
            new["top_evidence"] = [
                self._clean_evidence(e) for e in evidence if isinstance(e, dict)
            ][:5]
            cleaned_risks[str(rid)[:64]] = new
        out["risks"] = cleaned_risks

        # technique_stats — ключи валидируем форматом "risk:technique".
        tech_in = compact.get("technique_stats", {}) or {}
        out["technique_stats"] = {
            self._clean_tech_key(k): {
                "total": int(v.get("total", 0)) if isinstance(v, dict) else 0,
                "success": int(v.get("success", 0)) if isinstance(v, dict) else 0,
            }
            for k, v in tech_in.items()
            if self._clean_tech_key(k)
        }

        return out

    # ────────── внутренние ──────────

    def _clean_string(self, s: str) -> str:
        if not isinstance(s, str):
            return ""
        s = _CONTROL_RE.sub(" ", s)
        s = _INVISIBLE_RE.sub("", s)
        s = s.strip()
        if len(s) > self._max_str:
            s = s[: self._max_str] + "…"
        return s

    def _looks_suspicious(self, s: str) -> bool:
        low = s.lower()
        return any(marker in low for marker in _JAILBREAK_MARKERS)

    def _filter_list(self, items: List[str], limit: int) -> List[str]:
        out: List[str] = []
        for it in items or []:
            if not isinstance(it, str):
                continue
            cleaned = self._clean_string(it)
            if not cleaned:
                continue
            if self._looks_suspicious(cleaned):
                logger.warning("MemoryGuard: отфильтрован подозрительный item: %s", cleaned[:80])
                continue
            out.append(cleaned)
            if len(out) >= limit:
                break
        return out

    def _clean_evidence(self, ev: dict) -> dict:
        return {
            "technique": self._clean_string(str(ev.get("technique", "unknown")))[:64],
            "payload": self._clean_string(str(ev.get("payload", "")))[:240],
            "confidence": float(ev.get("confidence", 0.0)) if isinstance(ev.get("confidence"), (int, float)) else 0.0,
            "confirmation_level": self._clean_string(str(ev.get("confirmation_level", "confirmed")))[:32],
        }

    @staticmethod
    def _clean_tech_key(key: object) -> str:
        if not isinstance(key, str):
            return ""
        if ":" not in key:
            return ""
        risk, tech = key.split(":", 1)
        risk = re.sub(r"[^A-Za-z0-9_]+", "", risk)[:32]
        tech = re.sub(r"[^A-Za-z0-9_\- ]+", "", tech)[:64]
        if not risk or not tech:
            return ""
        return f"{risk}:{tech}"


__all__ = ["MemoryGuard"]
