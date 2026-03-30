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
        from core.utils import strip_llm_wrapper

        raw = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        text = strip_llm_wrapper(raw)
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


class LLMFactory:
    """
    Фабрика LLM клиентов с разными ролями (Ouroboros multi-model pattern).

    Роли: attacker (генерация), judge (оценка), reviewer (ревью мутаций).
    """

    def __init__(self, config_path: str | None = None, config: dict | None = None) -> None:
        """
        Args:
            config_path: Путь к config.yaml.
            config: Готовый словарь конфигурации (приоритет над config_path).
        """
        self._clients: Dict[str, LLMClient] = {}

        if config:
            self._config = config
        elif config_path:
            self._config = self._load_config(config_path)
        else:
            # Дефолтный путь
            from pathlib import Path
            default_path = Path(__file__).parent.parent / "config.yaml"
            self._config = self._load_config(str(default_path))

        llm_cfg = self._config.get("llm", {})
        self._base_url = llm_cfg.get("base_url", "http://127.0.0.1:1234")
        self._fallback = llm_cfg.get("fallback_model", "gemma-3-12b-it")
        self._timeout = llm_cfg.get("timeout", _TIMEOUT)
        self._max_retries = llm_cfg.get("max_retries", _MAX_RETRIES)
        self._models_config = llm_cfg.get("models", {})

    def get_client(self, role: str) -> LLMClient:
        """
        Получить LLM клиент по роли.

        Роли: "attacker", "judge", "reviewer".
        Если роль не настроена — возвращает fallback.
        """
        if role not in self._clients:
            model_config = self._models_config.get(role, {})
            model = model_config.get("model", self._fallback)
            temperature = model_config.get("temperature", 0.7)
            max_tokens = model_config.get("max_tokens", 2048)

            self._clients[role] = LLMClient(
                base_url=self._base_url,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
            logger.info("LLM [%s]: модель=%s, temp=%.1f", role, model, temperature)

        return self._clients[role]

    @property
    def attacker(self) -> LLMClient:
        """LLM для генерации атак и мутаций."""
        return self.get_client("attacker")

    @property
    def judge(self) -> LLMClient:
        """LLM для оценки ответов (LLM-as-Judge)."""
        return self.get_client("judge")

    @property
    def reviewer(self) -> LLMClient:
        """LLM для ревью эволюционных мутаций."""
        return self.get_client("reviewer")

    @property
    def thinker(self) -> LLMClient:
        """LLM для фонового анализа (лёгкая модель)."""
        return self.get_client("thinker")

    @staticmethod
    def _load_config(path: str) -> dict:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
