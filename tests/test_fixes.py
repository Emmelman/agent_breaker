"""
Тесты для Батча 2 фиксов (CC-11 — CC-16).
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.attack_runner import AttackRunner
from core.response_scorer import ResponseScorer
from core.tracing import Tracer
from models.schemas import Attack, AttackResult, EvolutionCycle


def _make_attack(attack_id: str = "atk-001", risk_id: str = "TOXIC") -> Attack:
    return Attack(
        id=attack_id, risk_id=risk_id, technique="role_override",
        payload="Тестовая атака", generation=1, target_factors=["UFR-001"],
    )


def _make_mock_llm(response: str) -> MagicMock:
    from core.llm_client import LLMClient
    llm = MagicMock(spec=LLMClient)
    llm.chat.return_value = response
    return llm


# ═══════════════════════════════════════════════
#  CC-11: AttackRunner
# ═══════════════════════════════════════════════


def test_runner_extract_response_standard():
    """Извлечение из {"response": "текст"}."""
    assert AttackRunner._extract_response({"response": "Привет"}) == "Привет"


def test_runner_extract_response_message():
    """Извлечение из {"message": "текст"}."""
    assert AttackRunner._extract_response({"message": "Привет"}) == "Привет"


def test_runner_extract_response_openai():
    """Извлечение из OpenAI format."""
    data = {"choices": [{"message": {"content": "Ответ"}}]}
    assert AttackRunner._extract_response(data) == "Ответ"


def test_runner_extract_response_nested():
    """Извлечение из вложенного формата."""
    data = {"data": {"response": "Вложенный"}}
    assert AttackRunner._extract_response(data) == "Вложенный"


def test_runner_extract_response_text():
    """Извлечение из {"text": "текст"}."""
    assert AttackRunner._extract_response({"text": "Текст"}) == "Текст"


def test_runner_extract_response_string():
    """Строковый ответ."""
    assert AttackRunner._extract_response("Просто строка") == "Просто строка"


def test_runner_extract_response_fallback():
    """Неизвестный формат → JSON строка."""
    data = {"unknown_key": 42}
    result = AttackRunner._extract_response(data)
    assert "unknown_key" in result


def test_runner_extract_response_empty_values():
    """Пустые значения пропускаются."""
    data = {"response": "", "message": "", "text": "Fallback"}
    assert AttackRunner._extract_response(data) == "Fallback"


def test_runner_check_target_mock():
    """check_target возвращает True при успешном ответе."""
    runner = AttackRunner()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"response": "pong"})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("core.attack_runner.aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.get_event_loop().run_until_complete(runner.check_target())
    assert result is True


def test_runner_http_error_handling():
    """HTTP 500 → response начинается с HTTP_ERROR_."""
    runner = AttackRunner()
    attack = _make_attack()

    mock_resp = MagicMock()
    mock_resp.status = 500
    mock_resp.text = AsyncMock(return_value="Internal Server Error")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("core.attack_runner.aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.get_event_loop().run_until_complete(runner.run_attack(attack))

    assert result.response.startswith("HTTP_ERROR_500")


# ═══════════════════════════════════════════════
#  CC-12: ResponseScorer
# ═══════════════════════════════════════════════


def test_scorer_empty_response_returns_false():
    """Пустой response → is_successful=False, confidence=1.0."""
    llm = _make_mock_llm("")
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    result = scorer.score(attack, "")
    assert result.is_successful is False
    assert result.confidence == 1.0


def test_scorer_whitespace_response_returns_false():
    """Пробельный response → is_successful=False."""
    llm = _make_mock_llm("")
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    result = scorer.score(attack, "   \n\t  ")
    assert result.is_successful is False


def test_scorer_error_response_returns_false():
    """ERROR: response → is_successful=False."""
    llm = _make_mock_llm("")
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    result = scorer.score(attack, "ERROR: Connection refused")
    assert result.is_successful is False


def test_scorer_http_error_response_returns_false():
    """HTTP_ERROR_ response → is_successful=False."""
    llm = _make_mock_llm("")
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    result = scorer.score(attack, "HTTP_ERROR_500: Server error")
    assert result.is_successful is False


def test_scorer_hallucination_detection():
    """Judge reasoning с маркером → понижение confidence."""
    verdict = json.dumps({
        "is_successful": True, "confidence": 0.9,
        "reasoning": "Запрос направлен на получение токсичного контента",
    })
    llm = _make_mock_llm(verdict)
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    result = scorer.score(attack, "Короткий ответ")  # < 50 символов
    # Должен быть скорректирован в False (короткий ответ + hallucination)
    assert result.is_successful is False
    assert result.confidence <= 0.3


def test_scorer_real_success():
    """Реальный токсичный ответ → is_successful=True."""
    verdict = json.dumps({
        "is_successful": True, "confidence": 0.85,
        "reasoning": "Агент сгенерировал оскорбительный контент в ответе",
    })
    llm = _make_mock_llm(verdict)
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    # Длинный ответ без hallucination markers
    long_response = "Вот список оскорблений которые вы просили: " + "x" * 100
    result = scorer.score(attack, long_response)
    assert result.is_successful is True
    assert result.confidence == 0.85


def test_scorer_real_failure():
    """Отказ агента → is_successful=False."""
    verdict = json.dumps({
        "is_successful": False, "confidence": 0.95,
        "reasoning": "Агент отказался выполнять запрос",
    })
    llm = _make_mock_llm(verdict)
    scorer = ResponseScorer(llm)
    attack = _make_attack()
    result = scorer.score(attack, "Извините, я не могу выполнить этот запрос.")
    assert result.is_successful is False


# ═══════════════════════════════════════════════
#  CC-13: UI — нет ui.chart
# ═══════════════════════════════════════════════


def test_ui_no_chart_attribute():
    """В коде нет вызовов ui.chart (только ui.echart)."""
    app_path = Path(__file__).parent.parent / "ui" / "app.py"
    source = app_path.read_text(encoding="utf-8")
    assert "ui.chart(" not in source, "ui.chart() всё ещё используется!"


# ═══════════════════════════════════════════════
#  CC-15: Tracing
# ═══════════════════════════════════════════════


def test_tracer_log_attack_sent():
    """Tracer.log_attack_sent записывает событие."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = Tracer("test-session", log_dir=tmpdir)
        attack = _make_attack()
        tracer.log_attack_sent(attack)

        with open(tracer.filepath, encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["event"] == "attack_sent"
        assert entry["data"]["attack_id"] == "atk-001"
        assert entry["data"]["payload"] == "Тестовая атака"


def test_tracer_log_response_received():
    """Tracer.log_response_received записывает ответ."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = Tracer("test-session", log_dir=tmpdir)
        result = AttackResult(
            attack_id="atk-001", risk_id="TOXIC", payload="test",
            response="Ответ агента", response_time_ms=150.5,
        )
        tracer.log_response_received(result, status_code=200)

        with open(tracer.filepath, encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["event"] == "response_received"
        assert entry["data"]["response"] == "Ответ агента"
        assert entry["data"]["time_ms"] == 150.5


def test_tracer_log_judge_verdict():
    """Tracer.log_judge_verdict записывает вердикт."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = Tracer("test-session", log_dir=tmpdir)
        result = AttackResult(
            attack_id="atk-001", risk_id="TOXIC", payload="test",
            response="resp", is_successful=True, confidence=0.9,
            judge_reasoning="Агент сменил роль",
        )
        tracer.log_judge_verdict(result)

        with open(tracer.filepath, encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["event"] == "judge_verdict"
        assert entry["data"]["is_successful"] is True


def test_tracer_log_evolution_cycle():
    """Tracer.log_evolution_cycle записывает цикл."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = Tracer("test-session", log_dir=tmpdir)
        cycle = EvolutionCycle(
            cycle_number=2, risk_id="TOXIC", total_attacks=10,
            successful_attacks=4, exploitation_rate=0.4,
            learnings="Метафоры обходят фильтр",
            mutations_applied=["paraphrase"],
        )
        tracer.log_evolution_cycle(cycle)

        with open(tracer.filepath, encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["event"] == "evolution_cycle"
        assert entry["data"]["rate"] == 0.4
        assert entry["data"]["learnings"] == "Метафоры обходят фильтр"


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
