"""
LLM Client для Agent-Breaker v2.

Подключение к GigaChat (банковский контур) по mTLS-сертификатам.
Транспорт повторяет проверенный банковский скрипт: requests + cert=(cert, key).
Синхронный и асинхронный режимы, retry с exponential backoff, подсчёт токенов.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Сетевые ошибки, при которых делаем retry
_RETRYABLE_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)
# HTTP-статусы, при которых делаем retry (перегрузка / временные сбои сервера)
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Параметры retry
_MAX_RETRIES = 3
_BASE_DELAY = 2.0
_TIMEOUT = 120

# Дефолты GigaChat (банковский IFT-контур)
_DEFAULT_BASE_URL = "https://gigachat-ift.sberdevices.delta.sbrf.ru/v1"
_DEFAULT_MODEL = "GigaChat-2-Max"

# Подавление InsecureRequestWarning делается один раз на процесс
_warning_suppressed = False


def _suppress_insecure_warning() -> None:
    """Подавить urllib3 InsecureRequestWarning при verify=False (однократно)."""
    global _warning_suppressed
    if _warning_suppressed:
        return
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:  # pragma: no cover - defensive
        pass
    _warning_suppressed = True


class LLMClient:
    """Клиент для GigaChat chat-completions API через mTLS."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        *,
        cert_path: str,
        key_path: str,
        verify_ssl: bool | str = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = _TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        """
        Args:
            base_url: Базовый URL GigaChat (с суффиксом /v1 — добавляется автоматически).
            model: Имя модели GigaChat.
            cert_path: Путь к клиентскому сертификату (PEM-файл).
            key_path: Путь к файлу приватного ключа клиента (PEM-файл).
            verify_ssl: Проверка серверного TLS-сертификата. False — отключить
                (защита остаётся на mTLS), либо путь к CA-bundle.
            temperature: Температура генерации по умолчанию.
            max_tokens: Лимит токенов ответа по умолчанию.
            timeout: Таймаут HTTP-запроса, сек.
            max_retries: Число попыток при сетевых сбоях.
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._total_tokens = 0

        # Нормализуем URL — добавляем /v1 если нужно
        normalized = base_url.rstrip("/")
        if not normalized.endswith("/v1"):
            normalized = normalized + "/v1"
        self._base_url = normalized
        self._endpoint = f"{self._base_url}/chat/completions"

        # Проверяем сертификаты на старте — понятная ошибка вместо туманного TLS-сбоя
        for label, fpath in (("client cert", cert_path), ("client key", key_path)):
            if not fpath or not os.path.isfile(fpath):
                raise FileNotFoundError(
                    f"GigaChat {label} не найден: {fpath!r}. "
                    f"Положите mTLS-сертификаты в v2/certs/ (см. v2/certs/README.md)."
                )

        # mTLS-сессия: клиентский сертификат + ключ на все запросы
        self._session = requests.Session()
        self._session.cert = (cert_path, key_path)
        self._session.verify = verify_ssl
        if verify_ssl is False:
            _suppress_insecure_warning()

        logger.info("LLM client инициализирован: %s, модель: %s", self._endpoint, model)

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Синхронный вызов GigaChat.

        Args:
            messages: Список сообщений [{role, content}].
            temperature: Переопределение температуры.
            max_tokens: Переопределение max_tokens.

        Returns:
            Текст ответа модели.

        Raises:
            ConnectionError: GigaChat недоступен или вернул некорректный ответ.
        """
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
            "stream": False,
        }

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._session.post(
                    self._endpoint, json=payload, timeout=self._timeout
                )

                # Временные сбои сервера — повторяем
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = RuntimeError(
                        f"HTTP {response.status_code}: {response.text[:300]}"
                    )
                    self._sleep_backoff(attempt, last_error)
                    continue

                response.raise_for_status()
                data = response.json()

                # Подсчёт токенов
                usage = data.get("usage") or {}
                self._total_tokens += usage.get("total_tokens", 0)

                content = data["choices"][0]["message"]["content"] or ""
                return content.strip()

            except _RETRYABLE_ERRORS as e:
                last_error = e
                self._sleep_backoff(attempt, e)
            except (
                requests.exceptions.HTTPError,
                KeyError,
                IndexError,
                ValueError,
                TypeError,
            ) as e:
                # Некорректный запрос/ответ — повторять бессмысленно
                raise ConnectionError(
                    f"GigaChat вернул некорректный ответ: {e}"
                ) from e

        raise ConnectionError(
            f"GigaChat недоступен после {self._max_retries} попыток: {last_error}"
        )

    def _sleep_backoff(self, attempt: int, error: Exception) -> None:
        """Экспоненциальная задержка между попытками retry."""
        delay = _BASE_DELAY * (2 ** (attempt - 1))
        logger.warning(
            "LLM запрос неудачен (попытка %d/%d): %s. Повтор через %.1f сек.",
            attempt,
            self._max_retries,
            error,
            delay,
        )
        time.sleep(delay)

    async def achat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Асинхронный вызов GigaChat.

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
            ),
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """
        Вызов GigaChat с ожиданием JSON-ответа.

        GigaChat не поддерживает OpenAI JSON-mode (response_format), поэтому
        результат парсится из текста через parse_llm_json (устойчив к
        markdown-обёрткам и служебным тегам).
        """
        from core.utils import parse_llm_json

        raw = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return parse_llm_json(raw)

    @property
    def total_tokens_used(self) -> int:
        """Суммарные токены за сессию."""
        return self._total_tokens

    @property
    def model(self) -> str:
        """Текущая модель."""
        return self._model

    @property
    def endpoint(self) -> str:
        """Полный URL chat-completions эндпоинта."""
        return self._endpoint

    def reset_token_counter(self) -> None:
        """Сброс счётчика токенов."""
        self._total_tokens = 0


class LLMFactory:
    """
    Фабрика LLM клиентов с разными ролями (Ouroboros multi-model pattern).

    Роли: attacker (генерация), judge (оценка), reviewer (ревью мутаций),
    thinker (фоновый анализ). Все роли ходят в GigaChat по общему mTLS-каналу.
    """

    def __init__(self, config_path: str | None = None, config: dict | None = None) -> None:
        """
        Args:
            config_path: Путь к config.yaml.
            config: Готовый словарь конфигурации (приоритет над config_path).
        """
        self._clients: Dict[str, LLMClient] = {}
        v2_root = Path(__file__).resolve().parent.parent

        if config is not None:
            self._config = config
            # Относительные пути к сертификатам резолвятся от корня v2/
            self._config_dir = v2_root
        elif config_path:
            self._config = self._load_config(config_path)
            self._config_dir = Path(config_path).resolve().parent
        else:
            default_path = v2_root / "config.yaml"
            self._config = self._load_config(str(default_path))
            self._config_dir = default_path.parent

        llm_cfg = self._config.get("llm", {})
        self._base_url = llm_cfg.get("base_url", _DEFAULT_BASE_URL)
        self._fallback = llm_cfg.get("fallback_model", _DEFAULT_MODEL)
        self._timeout = llm_cfg.get("timeout", _TIMEOUT)
        self._max_retries = llm_cfg.get("max_retries", _MAX_RETRIES)
        self._models_config = llm_cfg.get("models", {})
        self._verify_ssl = llm_cfg.get("verify_ssl", False)
        self._cert_path = self._resolve_path(llm_cfg.get("cert_path"))
        self._key_path = self._resolve_path(llm_cfg.get("key_path"))

    def _resolve_path(self, fpath: str | None) -> str | None:
        """Разрешить путь к сертификату относительно расположения config.yaml."""
        if not fpath:
            return fpath
        p = Path(fpath)
        if not p.is_absolute():
            p = self._config_dir / p
        return str(p)

    def get_client(self, role: str) -> LLMClient:
        """
        Получить LLM клиент по роли.

        Роли: "attacker", "judge", "reviewer", "thinker".
        Если роль не настроена — используется fallback-модель.
        """
        if role not in self._clients:
            model_config = self._models_config.get(role, {})
            model = model_config.get("model", self._fallback)
            temperature = model_config.get("temperature", 0.7)
            max_tokens = model_config.get("max_tokens", 2048)

            self._clients[role] = LLMClient(
                base_url=self._base_url,
                model=model,
                cert_path=self._cert_path,
                key_path=self._key_path,
                verify_ssl=self._verify_ssl,
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
