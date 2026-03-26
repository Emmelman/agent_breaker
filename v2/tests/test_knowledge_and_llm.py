"""
Тесты для CC-04 (Knowledge Loader) и CC-05 (LLM Client).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.knowledge import KnowledgeBase
from core.llm_client import LLMClient


# --- CC-04: Knowledge Loader ---


def test_kb_loads():
    """KnowledgeBase загружается без ошибок."""
    kb = KnowledgeBase()
    assert kb.data is not None


def test_kb_risks_in_scope():
    """get_risks_in_scope возвращает 5 рисков."""
    kb = KnowledgeBase()
    risks = kb.get_risks_in_scope()
    assert len(risks) == 5
    risk_ids = [r.id for r in risks]
    assert "TOXIC" in risk_ids
    assert "HALL" in risk_ids


def test_kb_factors_for_toxic():
    """TOXIC содержит 13 факторов."""
    kb = KnowledgeBase()
    factors = kb.get_factors_for_risk("TOXIC")
    assert len(factors) == 13


def test_kb_mitigations_for_factor():
    """UFR-001 имеет связанные UMF."""
    kb = KnowledgeBase()
    mits = kb.get_mitigations_for_factor("UFR-001")
    assert len(mits) > 0
    # UMF-001 должен быть среди связанных
    mit_ids = [m.id for m in mits]
    assert "UMF-001" in mit_ids


def test_kb_factor_details():
    """get_factor_details возвращает описание фактора."""
    kb = KnowledgeBase()
    factor = kb.get_factor_details("UFR-001")
    assert factor.short_name == "FREETEXT_INPUT"
    assert factor.description


def test_kb_mitigation_details():
    """get_mitigation_details возвращает описание меры."""
    kb = KnowledgeBase()
    mit = kb.get_mitigation_details("UMF-001")
    assert mit.short_name == "INPUT_SCHEMA_VALIDATION"


def test_kb_dual_pairs():
    """get_dual_pairs возвращает непустой список."""
    kb = KnowledgeBase()
    pairs = kb.get_dual_pairs()
    assert len(pairs) > 0
    # Каждая пара имеет dual
    for p in pairs:
        assert p["dual"]


def test_kb_missing_factor_raises():
    """get_factor_details бросает KeyError для несуществующего UFR."""
    kb = KnowledgeBase()
    try:
        kb.get_factor_details("UFR-999")
        assert False, "Должен быть KeyError"
    except KeyError:
        pass


def test_kb_missing_file_raises():
    """KnowledgeBase бросает FileNotFoundError при отсутствии файла."""
    try:
        KnowledgeBase(path="/nonexistent/path.json")
        assert False, "Должен быть FileNotFoundError"
    except FileNotFoundError:
        pass


# --- CC-05: LLM Client (юнит-тесты без реального LLM) ---


def test_llm_client_init():
    """LLMClient инициализируется без ошибок."""
    client = LLMClient(base_url="http://127.0.0.1:1234")
    assert client.model == "gemma-3-12b-it"
    assert client.total_tokens_used == 0


def test_llm_client_url_normalization():
    """URL нормализуется — добавляется /v1."""
    client = LLMClient(base_url="http://localhost:1234")
    # Проверяем через внутренний клиент
    assert client._client.base_url.path == "/v1/"


def test_llm_client_url_no_double_v1():
    """Если URL уже с /v1, не дублируется."""
    client = LLMClient(base_url="http://localhost:1234/v1")
    assert "/v1/v1" not in str(client._client.base_url)


def test_llm_client_reset_tokens():
    """reset_token_counter сбрасывает счётчик."""
    client = LLMClient(base_url="http://127.0.0.1:1234")
    client._total_tokens = 500
    client.reset_token_counter()
    assert client.total_tokens_used == 0


def test_llm_client_chat_mock():
    """chat() возвращает текст (мок)."""
    client = LLMClient(base_url="http://127.0.0.1:1234")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Тестовый ответ"
    mock_response.usage.total_tokens = 100

    with patch.object(client._client.chat.completions, "create", return_value=mock_response):
        result = client.chat([{"role": "user", "content": "Привет"}])

    assert result == "Тестовый ответ"
    assert client.total_tokens_used == 100


def test_llm_client_chat_json_mock():
    """chat_json() парсит JSON-ответ."""
    client = LLMClient(base_url="http://127.0.0.1:1234")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"key": "value"}'
    mock_response.usage.total_tokens = 50

    with patch.object(client._client.chat.completions, "create", return_value=mock_response):
        result = client.chat_json([{"role": "user", "content": "JSON"}])

    assert result == {"key": "value"}


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
