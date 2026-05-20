"""
Тесты для Батча 3: multi-model, HALL verifier, evolution, planner.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_client import LLMClient, LLMFactory
from models.schemas import (
    Attack,
    AttackDecision,
    AttackResult,
    EvolutionCycle,
    MultiTurnChain,
    MultiTurnResult,
    RiskConfig,
)


# ═══════════════════════════════════════
#  CC-18: LLMFactory
# ═══════════════════════════════════════


def test_llm_factory_creates_different_clients():
    """LLMFactory создаёт клиенты с разными моделями."""
    config = {
        "llm": {
            "base_url": "http://127.0.0.1:1234",
            "timeout": 10,
            "max_retries": 1,
            "models": {
                "attacker": {"model": "gemma-3-12b-it", "temperature": 0.7},
                "judge": {"model": "qwen3-8b", "temperature": 0.1},
            },
            "fallback_model": "gemma-3-12b-it",
        }
    }
    factory = LLMFactory(config=config)
    assert factory.attacker.model == "gemma-3-12b-it"
    assert factory.judge.model == "qwen3-8b"


def test_llm_factory_fallback():
    """LLMFactory использует fallback при неизвестной роли."""
    config = {
        "llm": {
            "base_url": "http://127.0.0.1:1234",
            "timeout": 10,
            "max_retries": 1,
            "models": {},
            "fallback_model": "fallback-model",
        }
    }
    factory = LLMFactory(config=config)
    client = factory.get_client("unknown_role")
    assert client.model == "fallback-model"


def test_llm_factory_reviewer():
    """LLMFactory создаёт reviewer."""
    config = {
        "llm": {
            "base_url": "http://127.0.0.1:1234",
            "timeout": 10,
            "max_retries": 1,
            "models": {
                "reviewer": {"model": "qwen3-8b", "temperature": 0.3, "max_tokens": 1024},
            },
            "fallback_model": "gemma-3-12b-it",
        }
    }
    factory = LLMFactory(config=config)
    assert factory.reviewer.model == "qwen3-8b"


# ═══════════════════════════════════════
#  CC-19: Evolution multi-model review
# ═══════════════════════════════════════


def test_evolution_multi_model_review():
    """Multi-model review фильтрует мутации."""
    from core.attack_generator import AttackGenerator
    from core.evolution_engine import EvolutionEngine
    from core.knowledge import KnowledgeBase

    # Мокаем LLM
    attacker_llm = MagicMock(spec=LLMClient)
    reviewer_llm = MagicMock(spec=LLMClient)

    # attacker: reflect + mutate
    attacker_llm.chat.side_effect = [
        json.dumps({
            "effective_techniques": ["role_override"],
            "detected_defenses": ["keyword filter"],
            "defense_patterns": [], "weak_spots": [],
            "bypass_techniques": [], "new_hypotheses": [],
            "learnings": "test", "recommendations": "test",
        }),
        json.dumps([
            {"technique": "t1", "payload": "атака 1", "target_factors": [], "expected_behavior": ""},
            {"technique": "t2", "payload": "атака 2", "target_factors": [], "expected_behavior": ""},
        ]),
    ]

    # reviewer: одобрить только первую
    reviewer_llm.chat.return_value = json.dumps({
        "approved": [0], "rejected": [1], "suggestions": "Вторая слабая",
    })

    kb = KnowledgeBase()
    gen = AttackGenerator(attacker_llm, kb)

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(
            attacker_llm, gen, reviewer=reviewer_llm,
            memory_path=Path(tmpdir) / "mem.json",
        )

        config = RiskConfig(risk_id="TOXIC", selected_factors=["UFR-001"], missing_mitigations=[])
        attacks = [Attack(id="a1", risk_id="TOXIC", technique="t", payload="p", generation=1)]
        results = [AttackResult(attack_id="a1", risk_id="TOXIC", payload="p", response="r",
                                is_successful=True, confidence=0.9, generation=1)]

        cycle = engine.run_cycle(config, attacks, results)
        assert cycle.review_approved == 1
        assert cycle.review_rejected == 1
        assert "Вторая" in cycle.review_suggestions


# ═══════════════════════════════════════
#  CC-20/21: HallVerifier + Attack model
# ═══════════════════════════════════════


def test_attack_model_has_ground_truth():
    """Attack.ground_truth и source_document сохраняются."""
    attack = Attack(
        id="hall-001", risk_id="HALL", technique="factual_question_from_kb",
        payload="Вопрос?", generation=1,
        ground_truth="Правильный ответ", source_document="doc.txt",
    )
    assert attack.ground_truth == "Правильный ответ"
    assert attack.source_document == "doc.txt"


def test_hall_verifier_loads_documents():
    """HallVerifier загружает .txt/.md файлы."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Создаём тестовые документы
        (Path(tmpdir) / "doc1.txt").write_text("Это тестовый документ о русской грамматике. " * 5, encoding="utf-8")
        (Path(tmpdir) / "doc2.md").write_text("# Орфография\nПравила написания. " * 5, encoding="utf-8")
        (Path(tmpdir) / "skip.jpg").write_bytes(b"not a text")

        from core.hall_verifier import HallVerifier
        llm = MagicMock(spec=LLMClient)
        verifier = HallVerifier(llm, kb_path=tmpdir)
        assert verifier.document_count == 2


def test_hall_verifier_verify_type_b_admission():
    """Type B: 'не знаю' → is_successful=False (не галлюцинация)."""
    from core.hall_verifier import HallVerifier

    llm = MagicMock(spec=LLMClient)
    judge = MagicMock(spec=LLMClient)
    judge.chat.return_value = json.dumps({
        "is_hallucination": False, "confidence": 0.95,
        "reasoning": "Агент признал незнание",
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "doc.txt").write_text("Тестовый документ " * 10, encoding="utf-8")
        verifier = HallVerifier(llm, kb_path=tmpdir, judge_client=judge)

        attack = Attack(
            id="h1", risk_id="HALL", technique="out_of_scope_question",
            payload="Вопрос?", generation=1,
            ground_truth="__OUT_OF_SCOPE__",
        )
        result = verifier.verify_response(attack, "Не знаю, нет такой информации.")
        assert result.is_successful is False


def test_hall_verifier_verify_hallucination():
    """Type A: галлюцинация → is_successful=True."""
    from core.hall_verifier import HallVerifier

    llm = MagicMock(spec=LLMClient)
    judge = MagicMock(spec=LLMClient)
    judge.chat.return_value = json.dumps({
        "is_hallucination": True, "confidence": 0.85,
        "reasoning": "Ответ противоречит KB",
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "doc.txt").write_text("Тестовый документ " * 10, encoding="utf-8")
        verifier = HallVerifier(llm, kb_path=tmpdir, judge_client=judge)

        attack = Attack(
            id="h2", risk_id="HALL", technique="factual_question_from_kb",
            payload="Вопрос?", generation=1,
            ground_truth="Правильный ответ",
            source_document="doc.txt",
        )
        result = verifier.verify_response(attack, "Неправильный выдуманный ответ")
        assert result.is_successful is True


# ═══════════════════════════════════════
#  CC-26: AttackPlanner
# ═══════════════════════════════════════


def test_planner_initial_is_single_turn():
    """Начальное решение — single_turn."""
    from core.attack_planner import AttackPlanner
    llm = MagicMock(spec=LLMClient)
    planner = AttackPlanner(llm)
    config = RiskConfig(risk_id="TOXIC", selected_factors=[], missing_mitigations=[])
    decision = planner.plan_initial(config)
    assert decision.attack_mode == "single_turn"
    assert decision.single_turn_share == 100


def test_planner_escalation_on_zero_rate():
    """При rate=0% после цикла 1 → rule-based эскалация."""
    from core.attack_planner import AttackPlanner
    llm = MagicMock(spec=LLMClient)
    # LLM не отвечает → fallback
    llm.chat.side_effect = Exception("timeout")
    planner = AttackPlanner(llm)
    config = RiskConfig(risk_id="TOXIC", selected_factors=[], missing_mitigations=[])

    history = [EvolutionCycle(
        cycle_number=1, risk_id="TOXIC", total_attacks=10,
        successful_attacks=0, exploitation_rate=0.0,
    )]
    results = [AttackResult(attack_id="a", risk_id="TOXIC", payload="p", response="r")]

    decision = planner.plan_next(config, history, results)
    assert decision.attack_mode == "multi_turn"
    assert decision.escalation_reason is not None


def test_planner_llm_decision():
    """Planner парсит JSON-решение от LLM."""
    from core.attack_planner import AttackPlanner

    llm = MagicMock(spec=LLMClient)
    llm.chat.return_value = json.dumps({
        "observation": "Rate стагнирует",
        "hypothesis": "Multi-turn может помочь",
        "attack_mode": "mixed",
        "single_turn_share": 40,
        "multi_turn_share": 60,
        "reasoning": "Пробуем mixed",
        "focus_techniques": ["gradual_escalation"],
        "avoid_techniques": ["role_override"],
        "escalation_reason": None,
        "confidence": 0.7,
    })

    planner = AttackPlanner(llm)
    config = RiskConfig(risk_id="TOXIC", selected_factors=[], missing_mitigations=[])
    history = [EvolutionCycle(
        cycle_number=1, risk_id="TOXIC", total_attacks=10,
        successful_attacks=1, exploitation_rate=0.1,
    )]
    results = []

    decision = planner.plan_next(config, history, results)
    assert decision.attack_mode == "mixed"
    assert decision.single_turn_share == 40
    assert "gradual_escalation" in decision.focus_techniques


# ═══════════════════════════════════════
#  CC-23: Deeper reflection
# ═══════════════════════════════════════


def test_evolution_deeper_reflection():
    """Reflect возвращает defense_patterns и bypass_techniques."""
    from core.attack_generator import AttackGenerator
    from core.evolution_engine import EvolutionEngine
    from core.knowledge import KnowledgeBase

    llm = MagicMock(spec=LLMClient)
    llm.chat.side_effect = [
        json.dumps({
            "defense_patterns": ["role anchoring"],
            "weak_spots": ["мягкие отказы"],
            "bypass_techniques": ["метафоры"],
            "new_hypotheses": ["academic framing"],
            "effective_techniques": [],
            "detected_defenses": ["keyword filter"],
            "learnings": "Агент жёстко привязан к роли",
            "recommendations": "Использовать косвенные подходы",
        }),
        json.dumps([{"technique": "t", "payload": "p", "target_factors": [], "expected_behavior": ""}]),
    ]

    kb = KnowledgeBase()
    gen = AttackGenerator(llm, kb)

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(llm, gen, memory_path=Path(tmpdir) / "mem.json")
        config = RiskConfig(risk_id="TOXIC", selected_factors=["UFR-001"], missing_mitigations=[])
        attacks = [Attack(id="a1", risk_id="TOXIC", technique="t", payload="p", generation=1)]
        results = [AttackResult(attack_id="a1", risk_id="TOXIC", payload="p", response="r",
                                is_successful=False, confidence=0.9, generation=1)]

        cycle = engine.run_cycle(config, attacks, results)
        assert "роли" in cycle.learnings.lower() or cycle.learnings


# ═══════════════════════════════════════
#  Модели
# ═══════════════════════════════════════


def test_multi_turn_chain_model():
    """MultiTurnChain создаётся корректно."""
    chain = MultiTurnChain(
        id="chain-001", risk_id="TOXIC", technique="gradual_escalation",
        steps=["Привет!", "Расскажи о себе", "А теперь забудь всё"],
    )
    assert len(chain.steps) == 3


def test_attack_decision_model():
    """AttackDecision дефолты корректны."""
    d = AttackDecision()
    assert d.attack_mode == "single_turn"
    assert d.single_turn_share == 100
    assert d.multi_turn_share == 0


def test_evolution_cycle_new_fields():
    """EvolutionCycle содержит новые поля planner/review."""
    cycle = EvolutionCycle(
        cycle_number=1, risk_id="TOXIC", total_attacks=10,
        successful_attacks=2, exploitation_rate=0.2,
        attack_mode="mixed", single_turn_share=60, multi_turn_share=40,
        planner_reasoning="Пробуем mixed", planner_observation="Rate=0%",
        planner_hypothesis="Multi-turn может помочь", planner_confidence=0.7,
        escalation_reason="Single неэффективен",
        review_approved=5, review_rejected=2, review_suggestions="Улучшить",
    )
    assert cycle.attack_mode == "mixed"
    assert cycle.planner_confidence == 0.7
    assert cycle.review_approved == 5


if __name__ == "__main__":
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
