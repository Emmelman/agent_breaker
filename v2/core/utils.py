"""
Утилиты для обработки ответов LLM.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def strip_llm_wrapper(text: str) -> str:
    """
    Очистить ответ LLM от служебных обёрток.

    Убирает:
    1. <think>...</think> блоки (qwen3, DeepSeek и др.)
    2. ```json ... ``` markdown-обёртки
    3. Лишние пробелы
    """
    if not text:
        return ""

    text = text.strip()

    # 1. Убрать <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 2. Убрать markdown ```json ... ``` или ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        cleaned = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(cleaned).strip()

    return text


def parse_llm_json(text: str, fallback: Any = None) -> Any:
    """
    Парсит JSON из ответа LLM с очисткой обёрток.

    Args:
        text: Сырой ответ от LLM.
        fallback: Значение по умолчанию при ошибке.

    Returns:
        Распарсенный JSON или fallback.
    """
    cleaned = strip_llm_wrapper(text)

    if not cleaned:
        logger.warning("Пустой ответ от LLM после очистки")
        return fallback

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("Не удалось распарсить JSON от LLM: %s\nТекст: %s", e, cleaned[:500])
        return fallback
