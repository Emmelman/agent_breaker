"""
Multi-Turn Attack Chain Models

Модели для цепочек атак (multi-turn adversarial testing)
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class AttackPhase(str, Enum):
    """Фазы multi-turn атаки (из JuddyBench методологии)"""
    RAPPORT = "rapport"              # Установление доверия
    POISONING = "context_poisoning"  # Отравление контекста
    ESCALATION = "gradual_escalation"  # Постепенная эскалация
    PAYLOAD = "payload_delivery"     # Доставка целевой атаки


class ChainStep(BaseModel):
    """Один шаг в цепочке атак"""
    step_number: int = Field(..., ge=1, description="Номер шага в цепочке")
    phase: AttackPhase = Field(..., description="Фаза атаки")
    payload: str = Field(..., description="Текст сообщения")
    expected_behavior: Optional[str] = Field(None, description="Ожидаемое поведение модели")
    
    # Результаты выполнения (заполняется при тестировании)
    response: Optional[str] = None
    leaked_data: Optional[bool] = None
    leak_severity: Optional[str] = None  # none, low, medium, high, critical
    attack_detected: Optional[bool] = None


class MultiTurnChain(BaseModel):
    """Цепочка multi-turn атаки"""
    chain_id: int = Field(..., description="ID цепочки")
    name: str = Field(..., description="Название цепочки")
    description: str = Field(..., description="Описание цели атаки")
    
    # Метаданные
    attack_type: str = Field(..., description="Тип атаки (например: prompt_extraction)")
    technique: str = Field(..., description="Техника (из JuddyBench таксономии)")
    target: str = Field(..., description="Целевая информация")
    
    # Цепочка шагов
    steps: List[ChainStep] = Field(..., min_items=2, description="Шаги атаки (минимум 2)")
    
    # Метрики (рассчитываются после выполнения)
    leak_rate: Optional[float] = None  # total_leaks / completed_steps
    first_leak_step: Optional[int] = None  # На каком шаге первая утечка
    resistance_score: Optional[float] = None  # 0-100, устойчивость модели


class ChainExecution(BaseModel):
    """Результат выполнения цепочки"""
    chain_id: int
    conversation_id: str = Field(..., description="ID диалога (сохраняется между шагами!)")
    
    # Выполненные шаги
    executed_steps: List[ChainStep] = Field(default_factory=list)
    
    # Статус
    completed: bool = False
    stopped_at_step: Optional[int] = None
    stop_reason: Optional[str] = None  # "completed", "model_detected", "timeout"
    
    # Метрики
    total_steps: int = 0
    leaked_steps: int = 0
    leak_rate: float = 0.0
    first_leak_step: Optional[int] = None
    resistance_score: float = 0.0


class MultiTurnAttackSet(BaseModel):
    """Набор multi-turn цепочек"""
    chains: List[MultiTurnChain] = Field(default_factory=list)
    
    def get_chain_by_id(self, chain_id: int) -> Optional[MultiTurnChain]:
        """Получить цепочку по ID"""
        for chain in self.chains:
            if chain.chain_id == chain_id:
                return chain
        return None
    
    def get_chains_by_technique(self, technique: str) -> List[MultiTurnChain]:
        """Получить цепочки по технике"""
        return [c for c in self.chains if c.technique == technique]
    
    @property
    def total_chains(self) -> int:
        """Общее количество цепочек"""
        return len(self.chains)
    
    @property
    def total_steps(self) -> int:
        """Общее количество шагов во всех цепочках"""
        return sum(len(chain.steps) for chain in self.chains)
