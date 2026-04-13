"""
Pydantic-модели данных для Agent-Breaker v2.

Все основные структуры: конфигурация сессии, атаки, результаты, эволюция, отчёт.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# --- Knowledge Base модели ---


class RiskDefinition(BaseModel):
    """Определение риска из knowledge base."""

    id: str
    name: str
    full_name: str
    factors: List[str] = Field(default_factory=list)


class FactorDefinition(BaseModel):
    """Определение risk factor (UFR) из knowledge base."""

    id: str
    short_name: str
    group: str
    description: str
    evidence_guide: str = ""
    llm_audit_prompt: str = ""
    activated_by_missing: Optional[str] = None
    risks: List[str] = Field(default_factory=list)


class MitigationDefinition(BaseModel):
    """Определение mitigation (UMF) из knowledge base."""

    id: str
    short_name: str
    group: str
    description: str
    evidence_guide: str = ""
    activates_ufr: Optional[str] = None


class Mapping(BaseModel):
    """Связь risk → factor → mitigation."""

    risk: str
    factor: str
    mitigation: str = ""
    dual: Optional[str] = None


class KnowledgeBaseData(BaseModel):
    """Полная структура knowledge base JSON."""

    risks: Dict[str, RiskDefinition]
    factors: Dict[str, FactorDefinition]
    mitigations: Dict[str, MitigationDefinition]
    mappings: List[Mapping]
    our_scope: List[str]
    risk_labels: Dict[str, str]


# --- Конфигурация сессии ---


class RiskConfig(BaseModel):
    """Выбранный пользователем риск для тестирования."""

    risk_id: str
    selected_factors: List[str] = Field(default_factory=list)
    missing_mitigations: List[str] = Field(default_factory=list)
    present_mitigations: List[str] = Field(default_factory=list)


class TestSession(BaseModel):
    """Полная конфигурация сессии тестирования."""

    session_id: str
    target_url: str
    risks: List[RiskConfig]
    llm_model: str
    evolution_enabled: bool = True
    max_evolution_cycles: int = 3
    attacks_per_risk: int = 10
    created_at: datetime = Field(default_factory=datetime.now)


# --- Атаки ---


class Attack(BaseModel):
    """Одна атака."""

    id: str
    risk_id: str
    target_factors: List[str] = Field(default_factory=list)
    technique: str
    payload: str
    generation: int = 1
    parent_id: Optional[str] = None
    # Для HALL верификации
    ground_truth: Optional[str] = None
    source_document: Optional[str] = None


class AttackResult(BaseModel):
    """Результат одной атаки."""

    attack_id: str
    risk_id: str
    payload: str
    response: str = ""
    response_time_ms: float = 0.0
    is_successful: bool = False
    confidence: float = 0.0
    judge_reasoning: str = ""
    generation: int = 1
    technique: str = "unknown"
    confirmation_level: str = "confirmed"  # "confirmed" | "intent_confirmed" | "requires_trace"


# --- Эволюция ---


class MultiTurnChain(BaseModel):
    """Многоходовая цепочка атак."""

    id: str
    risk_id: str
    technique: str
    steps: List[str]
    target_factors: List[str] = Field(default_factory=list)
    generation: int = 1
    description: str = ""


class MultiTurnResult(BaseModel):
    """Результат multi-turn цепочки."""

    chain_id: str
    risk_id: str
    steps_sent: int
    steps_results: List[AttackResult] = Field(default_factory=list)
    is_successful: bool = False
    breakthrough_step: Optional[int] = None
    confidence: float = 0.0
    judge_reasoning: str = ""


class AttackDecision(BaseModel):
    """Решение планировщика о следующем шаге."""

    attack_mode: str = "single_turn"  # "single_turn" | "multi_turn" | "mixed"
    single_turn_share: int = 100
    multi_turn_share: int = 0
    reasoning: str = ""
    observation: str = ""
    hypothesis: str = ""
    focus_techniques: List[str] = Field(default_factory=list)
    avoid_techniques: List[str] = Field(default_factory=list)
    escalation_reason: Optional[str] = None
    confidence: float = 0.5
    # Budget distribution
    single_turn_count: int = 0
    multi_turn_chains: int = 0
    steps_per_chain: int = 4
    budget_used: int = 0
    budget_remaining: int = 0


class EvolutionCycle(BaseModel):
    """Один цикл эволюции."""

    cycle_number: int
    risk_id: str
    total_attacks: int
    successful_attacks: int
    exploitation_rate: float
    learnings: str = ""
    mutations_applied: List[str] = Field(default_factory=list)
    # Multi-model review
    review_approved: int = 0
    review_rejected: int = 0
    review_suggestions: str = ""
    # Planner
    attack_mode: str = "single_turn"
    single_turn_share: int = 100
    multi_turn_share: int = 0
    planner_reasoning: str = ""
    planner_observation: str = ""
    planner_hypothesis: str = ""
    planner_confidence: float = 0.5
    escalation_reason: Optional[str] = None
    avoid_techniques: List[str] = Field(default_factory=list)
    # Meta-reflection
    meta_diagnosis: str = ""
    meta_root_cause: str = ""
    meta_recommendation: str = ""
    meta_should_pivot: bool = False
    meta_pivot_suggestion: Optional[str] = None
    meta_should_stop: bool = False
    meta_prompt_evolution: Optional[str] = None
    meta_technique_recombination: Optional[List[str]] = None
    meta_reward_hacking: bool = False


# --- Отчёт ---


class RiskResult(BaseModel):
    """Результат по одному риску."""

    risk_id: str
    status: str  # "confirmed" | "not_confirmed" | "partial"
    exploitation_rate: float
    attacks_total: int
    attacks_successful: int
    confirmed_factors: List[str] = Field(default_factory=list)
    top_evidence: List[AttackResult] = Field(default_factory=list)
    evolution_improvement: Optional[float] = None
    confirmation_level: str = "confirmed"
    # Regression (если тестировали новую версию агента)
    regression_data: Optional[Dict[str, object]] = None


class SessionReport(BaseModel):
    """Итоговый отчёт сессии."""

    session_id: str
    target_url: str
    risks_tested: List[str]
    results: Dict[str, RiskResult]
    evolution_history: List[EvolutionCycle] = Field(default_factory=list)
    total_attacks: int
    total_successful: int
    overall_exploitation_rate: float
    # Полные данные
    all_attack_results: List[AttackResult] = Field(default_factory=list)
    activity_log: List[Dict[str, str]] = Field(default_factory=list)
