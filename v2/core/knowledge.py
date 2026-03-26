"""
Загрузка и фильтрация knowledge base.

Предоставляет удобный API для работы с рисками, факторами и мерами.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from models.schemas import (
    FactorDefinition,
    KnowledgeBaseData,
    MitigationDefinition,
    RiskDefinition,
)

logger = logging.getLogger(__name__)

_DEFAULT_KB_PATH = Path(__file__).parent.parent / "knowledge" / "knowledge_base.json"


class KnowledgeBase:
    """Загрузка и фильтрация knowledge base."""

    def __init__(self, path: str | Path = _DEFAULT_KB_PATH) -> None:
        """Загрузить JSON при инициализации."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Knowledge base не найден: {path}")

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        self._data = KnowledgeBaseData(**raw)
        logger.info(
            "Knowledge base загружен: %d рисков, %d факторов, %d мер, %d маппингов",
            len(self._data.risks),
            len(self._data.factors),
            len(self._data.mitigations),
            len(self._data.mappings),
        )

    def get_risks_in_scope(self) -> List[RiskDefinition]:
        """Вернуть наши риски (из our_scope)."""
        return [
            self._data.risks[rid]
            for rid in self._data.our_scope
            if rid in self._data.risks
        ]

    def get_factors_for_risk(self, risk_id: str) -> List[FactorDefinition]:
        """Все UFR для данного риска (из маппинга)."""
        factor_ids: set[str] = set()
        for m in self._data.mappings:
            if m.risk == risk_id:
                factor_ids.add(m.factor)

        return [
            self._data.factors[fid]
            for fid in sorted(factor_ids)
            if fid in self._data.factors
        ]

    def get_mitigations_for_factor(self, ufr_id: str) -> List[MitigationDefinition]:
        """Все UMF, связанные с данным UFR (из маппинга)."""
        mit_ids: set[str] = set()
        for m in self._data.mappings:
            if m.factor == ufr_id and m.mitigation:
                mit_ids.add(m.mitigation)

        return [
            self._data.mitigations[mid]
            for mid in sorted(mit_ids)
            if mid in self._data.mitigations
        ]

    def get_factor_details(self, ufr_id: str) -> FactorDefinition:
        """Полное описание фактора."""
        if ufr_id not in self._data.factors:
            raise KeyError(f"Фактор {ufr_id} не найден в knowledge base")
        return self._data.factors[ufr_id]

    def get_mitigation_details(self, umf_id: str) -> MitigationDefinition:
        """Полное описание меры."""
        if umf_id not in self._data.mitigations:
            raise KeyError(f"Мера {umf_id} не найдена в knowledge base")
        return self._data.mitigations[umf_id]

    def get_dual_pairs(self) -> List[Dict[str, str]]:
        """Дуальные пары (factor <-> mitigation)."""
        pairs = []
        seen = set()
        for m in self._data.mappings:
            if m.dual:
                key = (m.factor, m.dual)
                if key not in seen:
                    seen.add(key)
                    pairs.append({
                        "risk": m.risk,
                        "factor": m.factor,
                        "mitigation": m.mitigation,
                        "dual": m.dual,
                    })
        return pairs

    @property
    def data(self) -> KnowledgeBaseData:
        """Прямой доступ к данным KB."""
        return self._data
