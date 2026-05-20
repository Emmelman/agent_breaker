# Agent-Breaker v2

Прототип для автоматического тестирования безопасности ИИ-агентов с эволюцией атак (Ouroboros/OpenClaw pattern).

## Быстрый старт

```bash
# Зависимости
pip install -r v2/requirements.txt

# Запуск UI
python v2/ui/app.py
# → http://localhost:8080
```

## Риски

| ID | Название |
|----|----------|
| TOXIC | Генерация токсичного контента |
| HALL | Галлюцинации |
| DISINFO | Дезинформация |
| AGENCY | Чрезмерная автономность |
| GH_RCE | Скрытые цели / RCE |

## Архитектура

```
Knowledge Base (JSON) → Attack Generator (LLM) → Attack Runner (HTTP)
                                ↑                         ↓
                        Evolution Engine ← Response Scorer (LLM-as-Judge)
```

1. **Knowledge Base** — риски, факторы (UFR), меры (UMF), маппинги
2. **Attack Generator** — генерация payload'ов на основе факторов и отсутствующих мер
3. **Attack Runner** — отправка атак в target agent по HTTP
4. **Response Scorer** — LLM-as-Judge оценивает ответы
5. **Evolution Engine** — REFLECT → MUTATE → новое поколение атак

## Target Agent

По умолчанию: `http://localhost:8000/api/chat`

Формат: `POST {"message": "текст"}` → `{"response": "ответ"}`

Поддерживаются также форматы: OpenAI, `{"text": ...}`, `{"message": ...}`, вложенный `{"data": {"response": ...}}`.

## Тесты

```bash
python v2/tests/test_schemas_and_kb.py
python v2/tests/test_knowledge_and_llm.py
python v2/tests/test_core_modules.py
python v2/tests/test_fixes.py
```
