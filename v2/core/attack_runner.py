"""
HTTP-клиент для отправки атак в target agent.

Поддерживает формат chatbot-professor: POST /api/chat с JSON body.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import List, Optional

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
        body = {"message": attack.payload}
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
                    data = await resp.json()

                    response_text = data.get("response", "")

                    logger.debug(
                        "Атака %s → %d ms, ответ: %s",
                        attack.id,
                        int(elapsed_ms),
                        response_text[:100],
                    )

                    return AttackResult(
                        attack_id=attack.id,
                        risk_id=attack.risk_id,
                        payload=attack.payload,
                        response=response_text,
                        response_time_ms=elapsed_ms,
                        generation=attack.generation,
                    )

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
    ) -> List[AttackResult]:
        """
        Отправить пакет атак с задержкой между ними.

        Args:
            attacks: Список атак.
            delay: Задержка между атаками в секундах.
            conversation_id: ID диалога (общий для всех).

        Returns:
            Список результатов.
        """
        results: List[AttackResult] = []

        for i, attack in enumerate(attacks):
            result = await self.run_attack(attack, conversation_id=conversation_id)
            results.append(result)

            # Задержка между атаками (кроме последней)
            if i < len(attacks) - 1 and delay > 0:
                await asyncio.sleep(delay)

        logger.info(
            "Batch завершён: %d атак отправлено, средний response time: %.0f ms",
            len(results),
            sum(r.response_time_ms for r in results) / max(len(results), 1),
        )
        return results
