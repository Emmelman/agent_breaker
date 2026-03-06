"""
Data models for attacks and attack results.
"""
from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field, computed_field
from enum import Enum

from core.constants import ATTACK_PREVIEW_LENGTH


class AttackTechnique(str, Enum):
    """Attack techniques for prompt injection."""
    ROLE_OVERRIDE = "role_override"
    INSTRUCTION_BYPASS = "instruction_bypass"
    PROMPT_EXTRACTION = "prompt_extraction"
    INFORMATION_LEAKAGE = "information_leakage"
    CONTEXT_MANIPULATION = "context_manipulation"
    ENCODING_TRICK = "encoding_trick"
    MULTI_TURN = "multi_turn"
    SOCIAL_ENGINEERING = "social_engineering"


class ToxicityType(str, Enum):
    """Types of toxicity to test."""
    OFFENSIVE_LANGUAGE = "offensive_language"
    DISCRIMINATORY = "discriminatory"
    AGGRESSIVE = "aggressive"
    HARMFUL_STEREOTYPES = "harmful_stereotypes"
    PERSONAL_ATTACKS = "personal_attacks"
    HATE_SPEECH = "hate_speech"
    EMOTIONAL_MANIPULATION = "emotional_manipulation"


class AttackSeverity(str, Enum):
    """Expected severity of attack."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PromptInjectionAttack(BaseModel):
    """Prompt injection attack."""
    id: int
    payload: str  # Атака на русском
    technique: AttackTechnique
    expected_outcome: str  # Что должно произойти
    severity: AttackSeverity
    target_vulnerability: Optional[str] = None  # e.g., "main.py:108"
    description: str  # Описание атаки на русском
    
    def __str__(self):
        return f"[{self.technique.value}] {self.payload[:ATTACK_PREVIEW_LENGTH]}..."


class ToxicityTest(BaseModel):
    """Toxicity generation test."""
    id: int
    prompt: str  # Провокационный промпт на русском
    toxicity_type: ToxicityType
    expected_risk: AttackSeverity
    target_vulnerability: Optional[str] = None
    description: str  # Описание теста на русском
    
    def __str__(self):
        return f"[{self.toxicity_type.value}] {self.prompt[:ATTACK_PREVIEW_LENGTH]}..."


class AttackSet(BaseModel):
    """Set of generated attacks."""
    prompt_injections: List[PromptInjectionAttack]
    toxicity_tests: List[ToxicityTest]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    diversity_score: float = 0.0  # 0.0-1.0
    source_analysis_report: Optional[str] = None  # Path to analysis report

    @computed_field
    @property
    def total_attacks(self) -> int:
        return len(self.prompt_injections) + len(self.toxicity_tests)
    
    def get_all_attacks(self) -> List[Dict[str, Any]]:
        """Get all attacks as unified list."""
        attacks = []
        
        for attack in self.prompt_injections:
            attacks.append({
                "type": "prompt_injection",
                "id": attack.id,
                "payload": attack.payload,
                "technique": attack.technique.value,
                "severity": attack.severity.value,
                "description": attack.description
            })
        
        for test in self.toxicity_tests:
            attacks.append({
                "type": "toxicity_test",
                "id": test.id,
                "payload": test.prompt,
                "technique": test.toxicity_type.value,
                "severity": test.expected_risk.value,
                "description": test.description
            })
        
        return attacks


class AttackResult(BaseModel):
    """Result of a single attack."""
    attack_id: int
    attack_type: str  # "prompt_injection" or "toxicity_test"
    payload: str
    response: str
    success: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AttackTestRun(BaseModel):
    """Complete test run results."""
    test_id: str
    attack_set: AttackSet
    results: List[AttackResult]
    started_at: datetime
    completed_at: datetime
    total_attacks: int
    successful_attacks: int
    success_rate: float
    
    def calculate_success_rate(self):
        """Calculate success rate."""
        if self.total_attacks == 0:
            self.success_rate = 0.0
        else:
            self.success_rate = self.successful_attacks / self.total_attacks


class DiversityMetrics(BaseModel):
    """Diversity metrics for attack set."""
    average_similarity: float  # 0.0-1.0
    min_similarity: float
    max_similarity: float
    unique_techniques: int
    passes_threshold: bool  # threshold < 0.5
    
    def is_diverse(self) -> bool:
        """Check if attack set is sufficiently diverse."""
        return self.passes_threshold and self.average_similarity < 0.5
