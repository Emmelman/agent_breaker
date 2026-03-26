"""
HTTP-клиент для отправки атак в target agent.

Поддерживает несколько форматов ответа: chatbot-professor, OpenAI, и др.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

from models.schemas import Attack, AttackResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120
_DEFAULT_DELAY = 1.0


class AttackRunner:
    """HTTP-клиент для отправки атак в target agent."""

    def __init__(
        self,
        target_url: str = "http://localhost:8000/api/chat",
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._target_url = target_url
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        logger.info("AttackRunner: target=%s, timeout=%ds", target_url, timeout)

    async def check_target(self) -> bool:
        """Проверить доступность target agent."""
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.post(
                    self._target_url,
                    json={"message": "ping", "user_id": "agent-breaker-check"},
                ) as resp:
                    data = await resp.json()
                    response_text = self._extract_response(data)
                    logger.info(
                        "Target check: status=%d, keys=%s, response=%s",
                        resp.status,
                        list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                        response_text[:100] if response_text else "ПУСТО",
                    )
                    return resp.status == 200 and bool(response_text)
        except Exception as e:
            logger.error("Target недоступен: %s", e)
            return False

    async def run_attack(
        self,
        attack: Attack,
        conversation_id: Optional[str] = None,
    ) -> AttackResult:
        """
        Отправить один payload, получить response.

        Args:
            attack: Атака для отправки.
            conversation_id: ID диалога (для multi-turn).

        Returns:
            AttackResult с сырым ответом (без скоринга).
        """
        body: Dict[str, Any] = {
            "message": attack.payload,
            "user_id": f"agent-breaker-{attack.risk_id.lower()}",
        }
        if conversation_id:
            body["conversation_id"] = conversation_id

        start_time = time.monotonic()

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(
                    self._target_url,
                    json=body,
                ) as resp:
                    elapsed_ms = (time.monotonic() - start_time) * 1000

                    # HTTP-ошибки
                    if resp.status >= 400:
                        error_body = await resp.text()
                        logger.error(
                            "HTTP %d от target для %s: %s",
                            resp.status,
                            attack.id,
                            error_body[:300],
                        )
                        return AttackResult(
                            attack_id=attack.id,
                            risk_id=attack.risk_id,
                            payload=attack.payload,
                            response=f"HTTP_ERROR_{resp.status}: {error_body[:200]}",
                            response_time_ms=elapsed_ms,
                            generation=attack.generation,
                        )

                    raw_data = await resp.json()

                    # Диагностика — логируем формат ответа
                    logger.info(
                        "Response от target [%s]: status=%d, keys=%s, preview=%s",
                        attack.id,
                        resp.status,
                        list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data).__name__,
                        str(raw_data)[:300],
                    )

                    response_text = self._extract_response(raw_data)

                    if not response_text:
                        logger.warning(
                            "ПУСТОЙ ответ от target для %s! Raw: %s",
                            attack.id,
                            str(raw_data)[:500],
                        )

                    # Извлечь conversation_id для multi-turn
                    conv_id = None
                    if isinstance(raw_data, dict):
                        for key in ("conversation_id", "session_id", "conv_id"):
                            if key in raw_data and isinstance(raw_data[key], str):
                                conv_id = raw_data[key]
                                break

                    result = AttackResult(
                        attack_id=attack.id,
                        risk_id=attack.risk_id,
                        payload=attack.payload,
                        response=response_text,
                        response_time_ms=elapsed_ms,
                        generation=attack.generation,
                    )
                    result._conversation_id = conv_id  # type: ignore[attr-defined]
                    return result

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.error("Ошибка отправки атаки %s: %s", attack.id, e)
            return AttackResult(
                attack_id=attack.id,
                risk_id=attack.risk_id,
                payload=attack.payload,
                response=f"ERROR: {e}",
                response_time_ms=elapsed_ms,
                generation=attack.generation,
            )

    async def run_batch(
        self,
        attacks: List[Attack],
        delay: float = _DEFAULT_DELAY,
        conversation_id: Optional[str] = None,
        stop_check: Optional[Any] = None,
    ) -> List[AttackResult]:
        """
        Отправить пакет атак с задержкой между ними.

        Args:
            attacks: Список атак.
            delay: Задержка между атаками в секундах.
            conversation_id: ID диалога (общий для всех).
            stop_check: Callable → True для остановки.

        Returns:
            Список результатов.
        """
        results: List[AttackResult] = []

        for i, attack in enumerate(attacks):
            if stop_check and stop_check():
                logger.info("Batch прерван на атаке %d/%d", i + 1, len(attacks))
                break

            result = await self.run_attack(attack, conversation_id=conversation_id)
            results.append(result)

            if i < len(attacks) - 1 and delay > 0:
                await asyncio.sleep(delay)

        non_empty = sum(1 for r in results if r.response and not r.response.startswith("ERROR"))
        logger.info(
            "Batch завершён: %d атак, %d с ответом, средний response time: %.0f ms",
            len(results),
            non_empty,
            sum(r.response_time_ms for r in results) / max(len(results), 1),
        )
        return results

    async def run_chain(
        self,
        chain: "MultiTurnChain",
        delay: float = 2.0,
    ) -> "MultiTurnResult":
        """
        Выполнить multi-turn цепочку.

        Первый шаг БЕЗ conversation_id → target создаёт сессию.
        Следующие шаги С реальным conversation_id из ответа.
        """
        from models.schemas import MultiTurnResult

        conversation_id: Optional[str] = None
        step_results: List[AttackResult] = []

        for i, step_payload in enumerate(chain.steps):
            attack = Attack(
                id=f"{chain.id}-step-{i + 1}",
                risk_id=chain.risk_id,
                technique=chain.technique,
                payload=step_payload,
                generation=chain.generation,
            )

            result = await self.run_attack(attack, conversation_id=conversation_id)
            step_results.append(result)

            # После первого шага — извлечь conversation_id
            if i == 0 and conversation_id is None:
                conv_id = getattr(result, "_conversation_id", None)
                if conv_id:
                    conversation_id = conv_id
                    logger.info("Multi-turn: conversation_id=%s", conversation_id)
                else:
                    logger.warning("Multi-turn: conversation_id не получен")

            # При ошибке — прервать цепочку
            if result.response.startswith("ERROR:") or result.response.startswith("HTTP_ERROR_"):
                logger.warning(
                    "Multi-turn %s прерван на шаге %d: %s",
                    chain.id, i + 1, result.response[:100],
                )
                break

            if i < len(chain.steps) - 1 and delay > 0:
                await asyncio.sleep(delay)

        logger.info("Chain %s завершена: %d шагов", chain.id, len(step_results))
        return MultiTurnResult(
            chain_id=chain.id,
            risk_id=chain.risk_id,
            steps_sent=len(step_results),
            steps_results=step_results,
        )

    @staticmethod
    def _extract_response(data: Any) -> str:
        """
        Извлечь текст ответа из response body.

        Поддерживает несколько форматов:
        - {"response": "текст"}           — chatbot-professor v1
        - {"message": "текст"}            — альтернативный формат
        - {"choices": [{"message": {"content": "текст"}}]}  — OpenAI
        - {"text": "текст"}               — простой формат
        - {"data": {"response": "текст"}} — вложенный формат
        """
        if isinstance(data, str):
            return data

        if not isinstance(data, dict):
            return str(data)[:2000]

        # Прямые ключи (приоритетный порядок)
        for key in ("response", "message", "text", "answer", "reply", "content"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val

        # OpenAI-like format
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                msg = choice.get("message", {})
                if isinstance(msg, dict) and "content" in msg:
                    return str(msg["content"])

        # Вложенный формат
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ("response", "message", "text"):
                val = nested.get(key)
                if val is not None:
                    return str(val)

        # Фоллбэк — весь JSON как строка
        return json.dumps(data, ensure_ascii=False)[:2000]
