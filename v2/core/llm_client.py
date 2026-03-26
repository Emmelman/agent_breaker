"""
LLM Client для Agent-Breaker v2.

Поддерживает OpenAI-compatible API (LLM Studio), синхронный и асинхронный режимы,
retry с exponential backoff, подсчёт токенов.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

logger = logging.getLogger(__name__)

# Ошибки, при которых делаем retry
_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)

# Параметры retry
_MAX_RETRIES = 3
_BASE_DELAY = 2.0
_TIMEOUT = 120


class LLMClient:
    """Клиент для OpenAI-compatible LLM API (LLM Studio)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234/v1",
        model: str = "gemma-3-12b-it",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = _TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._total_tokens = 0

        # Нормализуем URL — добавляем /v1 если нужно
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        self._client = OpenAI(
            base_url=base_url,
            api_key="not-needed",
            timeout=timeout,
        )
        logger.info("LLM client инициализирован: %s, модель: %s", base_url, model)

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Синхронный вызов LLM.

        Args:
            messages: Список сообщений [{role, content}].
            temperature: Переопределение температуры.
            max_tokens: Переопределение max_tokens.
            response_format: Формат ответа (например, {"type": "json_object"}).

        Returns:
            Текст ответа модели.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature if temperature is not None else self._temperature,
                    "max_tokens": max_tokens or self._max_tokens,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = self._client.chat.completions.create(**kwargs)

                # Подсчёт токенов
                if response.usage:
                    self._total_tokens += response.usage.total_tokens

                content = response.choices[0].message.content or ""
                return content.strip()

            except _RETRYABLE_ERRORS as e:
                last_error = e
                delay = _BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "LLM запрос неудачен (попытка %d/%d): %s. Повтор через %.1f сек.",
                    attempt,
                    self._max_retries,
                    e,
                    delay,
                )
                time.sleep(delay)

        raise ConnectionError(
            f"LLM недоступен после {self._max_retries} попыток: {last_error}"
        )

    async def achat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Асинхронный вызов LLM.

        Оборачивает синхронный вызов в asyncio executor,
        чтобы не блокировать event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            ),
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Вызов LLM с ожиданием JSON-ответа. Парсит результат."""
        raw = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        # Пробуем распарсить JSON даже если модель обернула в markdown
        text = raw.strip()
        if text.startswith("```"):
            # Убираем markdown-обёртку
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        return json.loads(text)

    @property
    def total_tokens_used(self) -> int:
        """Суммарные токены за сессию."""
        return self._total_tokens

    @property
    def model(self) -> str:
        """Текущая модель."""
        return self._model

    def reset_token_counter(self) -> None:
        """Сброс счётчика токенов."""
        self._total_tokens = 0
