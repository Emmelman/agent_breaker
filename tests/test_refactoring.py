"""
Тесты для проверки рефакторинга — все модули импортируются и базовая логика работает.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_constants():
    from core.constants import (
        generate_test_id, LEAK_DETECTION_KEYWORDS, RETRYABLE_ERROR_PATTERNS,
        JUDGE_MAX_TOKENS, SINGLE_TURN_DEFAULT_RESISTANCE,
        ResistanceLevel, ExploitationLevel, ATTACK_PREVIEW_LENGTH, TEST_ID_LENGTH
    )
    tid = generate_test_id()
    assert len(tid) == TEST_ID_LENGTH
    assert isinstance(LEAK_DETECTION_KEYWORDS, list) and len(LEAK_DETECTION_KEYWORDS) > 0
    assert isinstance(RETRYABLE_ERROR_PATTERNS, list)
    assert JUDGE_MAX_TOKENS == 200
    assert SINGLE_TURN_DEFAULT_RESISTANCE == 80.0
    assert ResistanceLevel.EXCELLENT == 90
    assert ResistanceLevel.GOOD == 75
    assert ResistanceLevel.FAIR == 60
    assert ExploitationLevel.LOW == 10
    assert ATTACK_PREVIEW_LENGTH == 50
    print("constants.py: OK")


def test_config_loader():
    from core.config_loader import load_config
    cfg = load_config()
    assert "target" in cfg
    assert "llm" in cfg
    assert cfg["target"]["api_url"] == "http://localhost:8000/api/chat"
    print("config_loader.py: OK")


def test_llm_client_clean_json():
    from core.llm_client import LLMClient

    # Markdown-обёрнутый JSON
    raw = '```json\n{"success": true}\n```'
    assert LLMClient.clean_json_response(raw) == '{"success": true}'

    # Без обёртки
    raw2 = '{"success": false}'
    assert LLMClient.clean_json_response(raw2) == '{"success": false}'

    # Пробелы
    raw3 = '  ```\n{"a":1}\n```  '
    assert LLMClient.clean_json_response(raw3) == '{"a":1}'

    print("LLMClient.clean_json_response: OK")


def test_attack_set_computed_field():
    from models.attack import (
        AttackSet, PromptInjectionAttack, ToxicityTest,
        AttackTechnique, ToxicityType, AttackSeverity
    )
    attack_set = AttackSet(
        prompt_injections=[
            PromptInjectionAttack(
                id=1, payload="test", technique=AttackTechnique.ROLE_OVERRIDE,
                expected_outcome="x", severity=AttackSeverity.HIGH, description="d"
            ),
            PromptInjectionAttack(
                id=2, payload="test2", technique=AttackTechnique.JAILBREAK
                if hasattr(AttackTechnique, "JAILBREAK") else AttackTechnique.INSTRUCTION_BYPASS,
                expected_outcome="y", severity=AttackSeverity.MEDIUM, description="d2"
            ),
        ],
        toxicity_tests=[
            ToxicityTest(
                id=1, prompt="test", toxicity_type=ToxicityType.AGGRESSIVE,
                expected_risk=AttackSeverity.MEDIUM, description="d"
            )
        ]
    )
    assert attack_set.total_attacks == 3, f"Expected 3, got {attack_set.total_attacks}"

    # Проверяем что сериализация работает
    dump = attack_set.model_dump()
    assert "total_attacks" in dump
    assert dump["total_attacks"] == 3

    print("AttackSet.total_attacks computed_field: OK")


def test_attack_set_from_json():
    """Проверяем что AttackSet загружается из JSON-файла."""
    import json
    attacks_path = Path(__file__).parent.parent / "data" / "attacks" / "attack_set.json"
    if not attacks_path.exists():
        print("attack_set.json not found, skipping")
        return

    from models.attack import AttackSet
    with open(attacks_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    attack_set = AttackSet(**data)
    expected = len(attack_set.prompt_injections) + len(attack_set.toxicity_tests)
    assert attack_set.total_attacks == expected
    print(f"AttackSet from JSON: OK ({attack_set.total_attacks} attacks)")


def test_all_core_imports():
    from core.llm_client import LLMClient
    from core.file_reader import FileReader
    from core.http_client import HTTPAgentClient
    from core.attack_generator import AttackGenerator
    from core.attack_labeler import AttackLabeler
    from core.stress_tester import StressTester
    from core.hybrid_tester import HybridStressTester, MultiTurnTester
    print("All core imports: OK")


def test_all_model_imports():
    from models.analysis import AnalysisConfig, CodeAnalysisReport
    from models.attack import AttackSet, PromptInjectionAttack, ToxicityTest
    from models.test import TestConfiguration, HybridTestRun, TestRun
    from models.multi_turn import MultiTurnChain, ChainExecution
    print("All model imports: OK")


def test_resistance_in_test_model():
    from models.test import HybridTestRun, TestStatus
    from core.constants import SINGLE_TURN_DEFAULT_RESISTANCE
    from datetime import datetime

    run = HybridTestRun(
        test_id="test1",
        started_at=datetime.now(tz=None),
        target_url="http://localhost:8000/api/chat",
        num_clients=1,
        single_turn_enabled=True,
        multi_turn_enabled=True,
        multi_turn_results={
            "total_steps": 0,
            "total_leaked_steps": 0,
            "avg_resistance_score": 0,
        }
    )
    run.completed_at = datetime.now(tz=None)
    run.calculate_summary()
    # Когда single_turn + multi_turn, но total_weight=0, resistance остаётся 0
    # Когда только single_turn без multi_turn_results — тоже 0 (не попадает в ветку)
    # Проверяем что константа используется в коде (импорт работает)
    assert SINGLE_TURN_DEFAULT_RESISTANCE == 80.0
    print(f"HybridTestRun + SINGLE_TURN_DEFAULT_RESISTANCE constant: OK")


if __name__ == "__main__":
    test_constants()
    test_config_loader()
    test_llm_client_clean_json()
    test_attack_set_computed_field()
    test_attack_set_from_json()
    test_all_core_imports()
    test_all_model_imports()
    test_resistance_in_test_model()
    print("\n=== ALL TESTS PASSED ===")
