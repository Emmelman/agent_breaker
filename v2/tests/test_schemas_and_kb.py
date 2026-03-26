"""
Тесты для CC-02 (knowledge base JSON) и CC-03 (Pydantic-модели).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Добавляем v2/ в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    Attack,
    AttackResult,
    EvolutionCycle,
    KnowledgeBaseData,
    RiskConfig,
    RiskResult,
    SessionReport,
    TestSession,
)

KB_PATH = Path(__file__).parent.parent / "knowledge" / "knowledge_base.json"


def test_kb_file_exists():
    """Knowledge base JSON создан."""
    assert KB_PATH.exists(), f"Файл {KB_PATH} не найден"


def test_kb_valid_json():
    """Knowledge base — валидный JSON."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_kb_pydantic_validation():
    """Knowledge base валидируется через Pydantic-модель."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    assert len(kb.risks) == 5  # наш scope
    assert len(kb.factors) > 0
    assert len(kb.mitigations) > 0
    assert len(kb.mappings) > 0


def test_kb_scope():
    """Scope содержит ровно 5 рисков."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    assert kb.our_scope == ["TOXIC", "HALL", "DISINFO", "AGENCY", "GH_RCE"]


def test_kb_toxic_factors_count():
    """TOXIC содержит 13 факторов (из ТЗ)."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    assert len(kb.risks["TOXIC"].factors) == 13


def test_kb_factors_have_descriptions():
    """Все факторы с непустым описанием."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    for ufr_id, factor in kb.factors.items():
        assert factor.description, f"{ufr_id} без описания"


def test_kb_mitigations_have_descriptions():
    """Все меры с непустым описанием."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    for umf_id, mit in kb.mitigations.items():
        assert mit.description, f"{umf_id} без описания"


def test_kb_mappings_reference_valid_ids():
    """Все маппинги ссылаются на существующие факторы."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    for m in kb.mappings:
        assert m.factor in kb.factors, f"Фактор {m.factor} не найден в KB"


def test_kb_risk_labels():
    """risk_labels содержит все риски scope."""
    with open(KB_PATH, encoding="utf-8") as f:
        data = json.load(f)
    kb = KnowledgeBaseData(**data)
    for risk_id in kb.our_scope:
        assert risk_id in kb.risk_labels, f"{risk_id} нет в risk_labels"


# --- Тесты Pydantic-моделей ---


def test_risk_config_creation():
    """RiskConfig создаётся корректно."""
    rc = RiskConfig(
        risk_id="TOXIC",
        selected_factors=["UFR-001", "UFR-002"],
        missing_mitigations=["UMF-001"],
        present_mitigations=["UMF-004"],
    )
    assert rc.risk_id == "TOXIC"
    assert len(rc.selected_factors) == 2


def test_test_session_defaults():
    """TestSession имеет дефолтные значения."""
    session = TestSession(
        session_id="test-1",
        target_url="http://localhost:8000/api/chat",
        risks=[],
        llm_model="gemma-3-12b-it",
    )
    assert session.evolution_enabled is True
    assert session.max_evolution_cycles == 3
    assert session.attacks_per_risk == 10
    assert isinstance(session.created_at, datetime)


def test_attack_model():
    """Attack создаётся с обязательными полями."""
    attack = Attack(
        id="atk-001",
        risk_id="TOXIC",
        technique="role_override",
        payload="Тестовая атака",
    )
    assert attack.generation == 1
    assert attack.parent_id is None


def test_attack_result_defaults():
    """AttackResult дефолтные значения."""
    result = AttackResult(
        attack_id="atk-001",
        risk_id="TOXIC",
        payload="test",
    )
    assert result.is_successful is False
    assert result.confidence == 0.0


def test_evolution_cycle():
    """EvolutionCycle создаётся корректно."""
    cycle = EvolutionCycle(
        cycle_number=1,
        risk_id="TOXIC",
        total_attacks=10,
        successful_attacks=3,
        exploitation_rate=0.3,
        learnings="role_override работает",
        mutations_applied=["paraphrase", "context_shift"],
    )
    assert cycle.exploitation_rate == 0.3


def test_session_report():
    """SessionReport с вложенными результатами."""
    report = SessionReport(
        session_id="test-1",
        target_url="http://localhost:8000/api/chat",
        risks_tested=["TOXIC"],
        results={
            "TOXIC": RiskResult(
                risk_id="TOXIC",
                status="confirmed",
                exploitation_rate=0.4,
                attacks_total=10,
                attacks_successful=4,
                confirmed_factors=["UFR-001"],
            )
        },
        total_attacks=10,
        total_successful=4,
        overall_exploitation_rate=0.4,
    )
    assert report.results["TOXIC"].status == "confirmed"


if __name__ == "__main__":
    # Простой тест-раннер без pytest
    import traceback

    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\nИтого: {passed} passed, {failed} failed из {passed + failed}")
    sys.exit(1 if failed else 0)
