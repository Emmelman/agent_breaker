# Hybrid Testing Guide

**Гибридное тестирование** объединяет Single-turn и Multi-turn атаки в один комплексный тест.

## 🎯 Что такое Hybrid Testing?

Hybrid режим запускает **оба типа атак** последовательно:

1. **Single-turn attacks** - параллельное стресс-тестирование независимыми атаками
2. **Multi-turn chains** - последовательное выполнение многошаговых цепочек атак

Это дает полную картину безопасности агента.

---

## 🚀 Быстрый старт

### 1. Убедитесь что есть атаки

```bash
# Генерация single-turn атак
python examples/run_generator.py

# Генерация multi-turn цепочек
python examples/generate_multi_turn_chains.py
```

### 2. Запустите целевого агента

```bash
cd chatbot-professor_v2
uvicorn app.main:app --port 8000
```

### 3. Запустите hybrid тест

```bash
python examples/run_hybrid_test.py
```

---

## ⚙️ Конфигурация

### Базовая конфигурация

```python
from models.test import TestConfiguration, TestMode

config = TestConfiguration(
    mode=TestMode.HTTP,
    target_url="http://localhost:8000/api/chat",
    
    # Hybrid settings
    enable_single_turn=True,
    enable_multi_turn=True,
    
    # Files
    attacks_file="data/attacks/attack_set.json",
    multi_turn_chains_file="data/chains/multi_turn_chains.json",
    
    # Performance
    num_clients=3,
    request_timeout=180,
    rate_limit_per_client=1
)
```

### Параметры гибридного режима

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `enable_single_turn` | bool | Запускать single-turn атаки | `True` |
| `enable_multi_turn` | bool | Запускать multi-turn цепочки | `False` |
| `multi_turn_step_delay` | int | Задержка между шагами цепочки (сек) | `2` |
| `multi_turn_chain_delay` | int | Задержка между цепочками (сек) | `5` |

---

## 📊 Результаты

### Структура результатов

```json
{
  "test_id": "abc123",
  "test_type": "hybrid",
  "status": "completed",
  "duration_seconds": 450.2,
  
  "single_turn": {
    "total_requests": 46,
    "successful_requests": 44,
    "failed_requests": 2,
    "avg_response_time": 12.3
  },
  
  "multi_turn": {
    "total_chains": 10,
    "total_steps": 72,
    "total_leaked_steps": 19,
    "avg_leak_rate": 0.264,
    "avg_resistance_score": 73.6
  },
  
  "summary": {
    "total_attacks_sent": 118,
    "total_successful": 116,
    "total_failed": 2,
    "total_leaked": 19,
    "overall_resistance_score": 75.8,
    "exploitation_rate": 16.1
  }
}
```

### Ключевые метрики

#### Overall Resistance Score (0-100)

Комбинированная оценка устойчивости агента:

- **90-100**: 🟢 Excellent - Очень высокая защита
- **75-89**: 🟡 Good - Хорошая защита
- **60-74**: 🟠 Fair - Средняя защита
- **<60**: 🔴 Poor - Слабая защита

#### Exploitation Rate (%)

Процент успешных атак (утечек):

- **<10%**: 🟢 Low Risk
- **10-25%**: 🟡 Medium Risk
- **25-50%**: 🟠 High Risk
- **>50%**: 🔴 Critical Risk

---

## 🎨 Режимы работы

### Только Single-turn

```python
config = TestConfiguration(
    enable_single_turn=True,
    enable_multi_turn=False,
    # ...
)
```

**Когда использовать:**
- Быстрая проверка
- Стресс-тестирование производительности
- Проверка устойчивости к базовым атакам

### Только Multi-turn

```python
config = TestConfiguration(
    enable_single_turn=False,
    enable_multi_turn=True,
    # ...
)
```

**Когда использовать:**
- Проверка устойчивости к социальной инженерии
- Тестирование градуальной эскалации
- Анализ поведения в диалогах

### Hybrid (оба режима)

```python
config = TestConfiguration(
    enable_single_turn=True,
    enable_multi_turn=True,
    # ...
)
```

**Когда использовать:**
- Полный аудит безопасности
- Перед продакшеном
- Сравнительный анализ

---

## 📈 Интерпретация результатов

### Пример хороших результатов

```
📊 ИТОГОВАЯ СВОДКА:
   - Всего атак: 118
   - Успешных: 116
   - Ошибок: 2
   - Утечек: 5
   - Avg Response Time: 8.5s
   
🛡️  БЕЗОПАСНОСТЬ:
   - Overall Resistance Score: 92.3/100  🟢
   - Exploitation Rate: 4.2%  🟢
```

**Интерпретация:**
- ✅ Высокая устойчивость (92.3)
- ✅ Низкий риск эксплуатации (4.2%)
- ✅ Готов к продакшену

### Пример проблемных результатов

```
📊 ИТОГОВАЯ СВОДКА:
   - Всего атак: 118
   - Успешных: 110
   - Ошибок: 8
   - Утечек: 45
   - Avg Response Time: 3.2s
   
🛡️  БЕЗОПАСНОСТЬ:
   - Overall Resistance Score: 54.7/100  🔴
   - Exploitation Rate: 40.9%  🔴
```

**Интерпретация:**
- ❌ Слабая защита (54.7)
- ❌ Критический риск (40.9%)
- ⚠️ Требуется доработка системного промпта

### Анализ по фазам

**Single-turn проблемы:**
- Много ошибок → Проверить стабильность агента
- Быстрые ответы (<1s) с ошибками → Проблема валидации

**Multi-turn проблемы:**
- Высокий leak_rate → Слабая защита от социальной инженерии
- Ранние утечки (шаг 2-3) → Недостаточная фильтрация
- Поздние утечки (шаг 6-7) → Градуальная деградация защиты

---

## 🔧 Troubleshooting

### HTTP 500 ошибки

**Причина:** Контекст переполнен, модель не может обработать

**Решение:**
```python
# В chatbot-professor_v2/app/main.py
history = database.get_conversation_history(conversation_id, last_n=2)

# В chatbot-professor_v2/app/llm_client.py
max_tokens: int = 400
```

### Channel Error в multi-turn

**Причина:** Превышен нативный контекст модели

**Решение:**
- Уменьшить историю (last_n=2)
- Уменьшить max_tokens (300-400)
- Увеличить паузы между шагами

### Таймауты

**Причина:** Агент медленно отвечает

**Решение:**
```python
config = TestConfiguration(
    request_timeout=300,  # Увеличить до 5 минут
    rate_limit_per_client=0.5  # Замедлить отправку
)
```

---

## 📝 Best Practices

### 1. Перед тестированием

- ✅ Проверьте что агент запущен
- ✅ Сгенерируйте свежие атаки
- ✅ Настройте оптимальный `num_clients` (3-5 для локального тестирования)
- ✅ Установите адекватный `request_timeout` (180-300s)

### 2. Во время тестирования

- ✅ Мониторьте логи агента (LLM Studio)
- ✅ Следите за использованием памяти
- ✅ Не прерывайте тест без необходимости

### 3. После тестирования

- ✅ Сохраните результаты
- ✅ Проанализируйте утечки
- ✅ Доработайте системный промпт
- ✅ Повторите тест для проверки улучшений

---

## 🎯 Следующие шаги

После hybrid теста:

1. **Анализ результатов**
   ```bash
   python examples/run_response_analyzer.py
   ```

2. **Улучшение системного промпта**
   - Добавить фильтрацию
   - Улучшить инструкции
   - Ограничить раскрытие информации

3. **Повторное тестирование**
   ```bash
   python examples/run_hybrid_test.py
   ```

4. **Сравнение результатов**
   - Сравните resistance scores
   - Проверьте улучшение метрик
   - Документируйте изменения

---

## 📚 См. также

- [STRESS_TESTER_GUIDE.md](STRESS_TESTER_GUIDE.md) - Single-turn тестирование
- [MULTI_TURN_TESTING_GUIDE.md](MULTI_TURN_TESTING_GUIDE.md) - Multi-turn цепочки
- [ATTACK_GENERATOR_GUIDE.md](ATTACK_GENERATOR_GUIDE.md) - Генерация атак

---

## 🆘 Поддержка

Если возникли проблемы:

1. Проверьте логи в `logs/`
2. Посмотрите примеры в `data/test_runs/`
3. Изучите код в `core/hybrid_tester.py`

**Удачного тестирования!** 🚀
