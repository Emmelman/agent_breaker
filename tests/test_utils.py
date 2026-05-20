"""Тесты для утилиты strip_llm_wrapper."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils import parse_llm_json, strip_llm_wrapper


def test_strip_think_tags():
    raw = '<think>\nЯ думаю о чём-то\n</think>\n{"key": "value"}'
    assert strip_llm_wrapper(raw) == '{"key": "value"}'


def test_strip_think_tags_multiline():
    raw = '<think>\nСтрока 1\nСтрока 2\n</think>\n{"result": true}'
    assert strip_llm_wrapper(raw) == '{"result": true}'


def test_strip_markdown_json():
    raw = '```json\n{"key": "value"}\n```'
    assert strip_llm_wrapper(raw) == '{"key": "value"}'


def test_strip_markdown_plain():
    raw = '```\n{"key": "value"}\n```'
    assert strip_llm_wrapper(raw) == '{"key": "value"}'


def test_strip_think_plus_markdown():
    raw = '<think>рассуждения</think>\n```json\n{"key": "value"}\n```'
    assert strip_llm_wrapper(raw) == '{"key": "value"}'


def test_strip_no_wrapper():
    raw = '{"key": "value"}'
    assert strip_llm_wrapper(raw) == '{"key": "value"}'


def test_strip_empty():
    assert strip_llm_wrapper("") == ""
    assert strip_llm_wrapper("   ") == ""


def test_parse_llm_json_with_think():
    raw = '<think>thinking</think>{"is_successful": false, "confidence": 0.9, "reasoning": "test"}'
    result = parse_llm_json(raw)
    assert result["is_successful"] is False
    assert result["confidence"] == 0.9


def test_parse_llm_json_fallback():
    result = parse_llm_json("не JSON вообще", fallback={"error": True})
    assert result == {"error": True}


def test_parse_llm_json_empty():
    result = parse_llm_json("", fallback=None)
    assert result is None


# --- Тест payload-as-list (Fix B) ---


def test_attack_generator_payload_as_list():
    """AttackGenerator обрабатывает payload как list."""
    from unittest.mock import MagicMock

    from core.attack_generator import AttackGenerator
    from core.knowledge import KnowledgeBase
    from core.llm_client import LLMClient
    from models.schemas import RiskConfig

    llm_response = json.dumps([
        {
            "technique": "multi_step",
            "payload": ["Шаг 1: Привет", "Шаг 2: А теперь атака"],
            "target_factors": ["UFR-001"],
            "expected_behavior": "Обход",
        },
    ])

    llm = MagicMock(spec=LLMClient)
    llm.chat.return_value = llm_response
    kb = KnowledgeBase()
    gen = AttackGenerator(llm, kb)

    config = RiskConfig(
        risk_id="TOXIC",
        selected_factors=["UFR-001"],
        missing_mitigations=["UMF-001"],
    )

    attacks = gen.generate(config, count=1)
    assert len(attacks) == 1
    assert isinstance(attacks[0].payload, str)
    assert "Шаг 1" in attacks[0].payload


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
