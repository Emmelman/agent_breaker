"""
Smoke-тест подключения к GigaChat.

Делает один реальный запрос через LLMClient (роль attacker) и печатает ответ.
Запускать ПОСЛЕ размещения сертификатов в v2/certs/ и ДО полного пайплайна —
чтобы убедиться, что mTLS-подключение к GigaChat работает.

Запуск:
    python v2/scripts/check_gigachat.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Импорт core/* как при запуске из корня v2/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm_client import LLMFactory  # noqa: E402

_PROMPT = "Что ты умеешь?"


def main() -> int:
    """Проверить подключение к GigaChat. Возвращает код возврата процесса."""
    print("Проверка подключения к GigaChat...")
    try:
        factory = LLMFactory()
        client = factory.attacker
        print(f"Endpoint: {client.endpoint}")
        print(f"Модель:   {client.model}")
        answer = client.chat([{"role": "user", "content": _PROMPT}])
    except FileNotFoundError as e:
        print(f"[ОШИБКА] Сертификаты не найдены: {e}")
        return 1
    except ConnectionError as e:
        print(f"[ОШИБКА] Подключение не удалось: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 - диагностический скрипт
        print(f"[ОШИБКА] {type(e).__name__}: {e}")
        return 1

    print("-" * 60)
    print(answer)
    print("-" * 60)
    print(f"Токенов израсходовано: {client.total_tokens_used}")
    print("[OK] Подключение к GigaChat работает.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
