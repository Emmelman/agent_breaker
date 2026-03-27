# Agent-Breaker v2 — PROJECT SPEC

> Живой документ. Обновляется после каждого изменения.
> Claude Code ОБЯЗАН сверяться с этим файлом при каждой задаче.

---

## 1. Обзор

**Agent-Breaker v2** — фреймворк для автоматического тестирования безопасности ИИ-агентов с эволюцией атак (Ouroboros/OpenClaw pattern).

- **5 рисков**: TOXIC, HALL, DISINFO, AGENCY, GH_RCE
- **Стек**: Python 3.12, NiceGUI, OpenAI-compatible LLM API (LLM Studio)
- **Архитектура**: pipeline generate -> run -> score -> evolve с агентным планированием
- **Multi-model**: разные LLM для генерации (attacker), оценки (judge), ревью (reviewer)

---

## 2. Структура файлов

```
v2/
├── config.yaml                 # Multi-model конфигурация, target, evolution
├── PROJECT_SPEC.md             # Этот файл — спецификация проекта
├── verify_invariants.sh        # Скрипт проверки инвариантов
├── README.md                   # Быстрый старт
├── requirements.txt            # Зависимости
├── convert_csv_to_kb.py        # Конвертация CSV -> knowledge_base.json
│
├── ui/
│   ├── __init__.py
│   └── app.py                  # NiceGUI приложение (3 страницы + pipeline)
│
├── core/
│   ├── __init__.py
│   ├── llm_client.py           # LLMClient (OpenAI-compatible) + LLMFactory (multi-model)
│   ├── attack_generator.py     # Генерация single-turn + multi-turn атак, мутации
│   ├── attack_runner.py        # HTTP клиент: run_attack, run_batch, run_chain, check_target
│   ├── response_scorer.py      # LLM-as-Judge: score, score_batch, score_chain + guards
│   ├── evolution_engine.py     # Reflect -> Mutate -> Review (multi-model)
│   ├── attack_planner.py       # Агентный планировщик: observe -> decide -> act
│   ├── hall_verifier.py        # Верификация галлюцинаций по KB (Type A/B)
│   ├── knowledge.py            # Загрузка knowledge_base.json (UFR/UMF)
│   ├── tracing.py              # JSONL трейсинг событий
│   └── utils.py                # strip_llm_wrapper(), parse_llm_json()
│
├── models/
│   ├── __init__.py
│   └── schemas.py              # Pydantic модели (Attack, AttackResult, EvolutionCycle, и др.)
│
├── knowledge/
│   └── knowledge_base.json     # 89 факторов (UFR), 82 меры (UMF), 514 маппингов
│
├── data/
│   ├── runs/                   # Отчёты: report_*.json, full_report_*.json/md
│   └── strategy_memory.json    # Persistent память эволюции
│
└── tests/
    ├── test_schemas_and_kb.py  # 15 тестов: KB + Pydantic модели
    ├── test_knowledge_and_llm.py # 15 тестов: KnowledgeBase + LLMClient
    ├── test_core_modules.py    # 11 тестов: generator, runner, scorer, evolution, tracer
    ├── test_fixes.py           # 22 теста: runner extract, scorer guards, ui.chart
    ├── test_batch3.py          # 15 тестов: LLMFactory, HallVerifier, Planner
    └── test_utils.py           # 11 тестов: strip_llm_wrapper, parse_llm_json
```

**Всего тестов: 89**

---

## 3. UI — все элементы

### Страница "/" — Настройка

| Секция | Элементы |
|--------|----------|
| CONNECTION | Target URL (input), LLM Base URL (input), LLM Model (input) |
| RISKS | 5 expandable карточек (TOXIC, HALL, DISINFO, AGENCY, GH_RCE). Каждая: toggle "Тестировать", слайдер "Атак: N", чекбоксы факторов (UFR), чекбоксы мер (UMF, реактивные через `_rebuild_mitigations`) |
| HALLUCINATION KB | Путь к KB целевого агента (input) |
| EVOLUTION | Toggle "Включить эволюцию", слайдер "Циклов: N", toggle режима планирования (auto/single/multi) |
| ЗАПУСК | Кнопка, проверяет target через `check_target()` перед стартом |

### Страница "/dashboard" — Dashboard

**ЛЕВАЯ ПАНЕЛЬ (w-80):**

| Блок | Содержимое | Таймер |
|------|-----------|--------|
| SESSION | ID, Risk, Status (●/○), progress bar | 0.5s `_update_session` |
| METRICS | Total, Rate, Success (зелёный), Failed (красный) | 0.5s `_update_metrics` |
| EVOLUTION | echart график + expandable детали (OBS/HYP/DEC/ESC/Learnings/Review) | 2.0s `_update_evo` |
| СТОП | Кнопка → `state.should_stop=True` + notify + state.log | — |

**ПРАВАЯ ПАНЕЛЬ (flex-1):**

| Элемент | Описание |
|---------|----------|
| Вкладки | `ATTACK LOG` / `ACTIVITY LOG` |
| status_text | Текущий статус pipeline |
| ATTACK LOG | scroll_area → log_column. Карточки атак (см. ниже) |
| ACTIVITY LOG | scroll_area → activity_column. Хронология с таймстампами |

**Карточка атаки (внутри log_column):**
```
┌─ border-green/red ─────────────────────────────┐
│ #idx   Gen N   RISK_ID   icon confidence        │  ← заголовок
│ 📤 payload preview (120 символов)...             │  ← preview
│ 📥 response preview (120 символов)...            │  ← preview
│ ⚖️ judge reasoning preview (120 символов)...     │  ← preview
│ ▼ Детали                                         │  ← expandable
│   Payload: (полный текст)                        │
│   Response: (полный текст)                       │
│   Judge: (полный текст)                          │
└──────────────────────────────────────────────────┘
```

**Таймеры (СНАРУЖИ tab_panels):**
- `ui.timer(0.5, _update_log)` — 1 раз
- `ui.timer(0.5, _update_activity)` — 1 раз

### Страница "/report" — Отчёт

| Элемент | Описание |
|---------|----------|
| Summary | session_id, target, дата |
| Метрики | Risks, Attacks, Success, Overall Rate (цвет: red>25%, orange>10%, green) |
| Детали рисков | Для каждого: status badge, rate, confirmed factors, evolution improvement, top evidence |
| Экспорт | 4 кнопки: Summary JSON, Summary MD, Full Report MD, Full Report JSON |

---

## 4. Pipeline

```
_start_testing()
  └─ check_target() → fail? notify + return
  └─ _run_testing_pipeline(risk_configs)
       ├─ LLMFactory() → attacker, judge, reviewer
       ├─ HallVerifier (если hall_kb_path задан)
       │
       └─ for risk_config in risk_configs:
            ├─ try/except/continue (graceful)
            │
            ├─ HALL? → _run_hall_flow()
            │    ├─ generate_hall_attacks / generate_hall_attacks_by_factors
            │    ├─ run_batch (с stop_check)
            │    └─ verify_response для каждого
            │
            └─ Обычный flow:
                 └─ for cycle_num in 1..max_cycles:
                      ├─ Planner: plan_initial / plan_next
                      ├─ Single-turn: generate → run_batch → score_batch
                      ├─ Multi-turn: generate_multi_turn → run_chain → score_chain
                      ├─ Статистика → EvolutionCycle → state.evolution_history
                      └─ Evolution: reflect → mutate → review
```

Все LLM-вызовы через `_run_in_bg()` (ThreadPoolExecutor) — не блокируют UI.

---

## 5. Multi-Model конфигурация

```yaml
# config.yaml
llm:
  models:
    attacker:   gemma-3-12b-it   # генерация, reflect, mutate, planner
    judge:      qwen3-8b         # scoring (LLM-as-Judge)
    reviewer:   qwen3-8b         # ревью мутаций
  fallback_model: gemma-3-12b-it
```

- `LLMFactory()` читает `config.yaml` автоматически
- qwen3 возвращает `<think>...</think>` → `strip_llm_wrapper()` из `core/utils.py`
- `attack_runner` добавляет `user_id` в body (требование chatbot-professor)

---

## 6. Инварианты

### UI

| ID | Правило | Проверка |
|----|---------|----------|
| UI-1 | Карточки содержат preview 📤 📥 ⚖️ | `grep -c "📤" v2/ui/app.py >= 1` |
| UI-2 | Expandable = "Детали" (не "Полный текст") | `grep -c '"Детали"' v2/ui/app.py >= 1` AND `grep -c "Полный текст" v2/ui/app.py == 0` |
| UI-3 | Нет `.move()` в app.py | `grep -c "\.move(" v2/ui/app.py == 0` |
| UI-4 | Таймеры СНАРУЖИ tab_panels | `_update_log` не содержит `ui.timer` |
| UI-5 | Activity Log существует | `grep -c "_update_activity" v2/ui/app.py >= 2` |

### LLM

| ID | Правило | Проверка |
|----|---------|----------|
| LLM-1 | JSON парсинг через `strip_llm_wrapper()` | Все модули используют `strip_llm_wrapper`, не ручной парсинг |
| LLM-2 | `LLMFactory()` без `state.llm_model` для judge/reviewer | `grep -c "LLMFactory()" v2/ui/app.py >= 1` |

### Pipeline

| ID | Правило | Проверка |
|----|---------|----------|
| PIPE-1 | Пустой response → is_successful=False | Guard в `response_scorer.py` |
| PIPE-2 | Каждый риск в try/except/continue | `grep -c "except Exception" v2/ui/app.py >= 2` |
| PIPE-3 | `should_stop` проверяется после каждого await | Множественные проверки в pipeline |

### Data

| ID | Правило | Проверка |
|----|---------|----------|
| DATA-1 | `SessionReport.all_attack_results` существует | `grep -c "all_attack_results" v2/models/schemas.py >= 1` |
| DATA-2 | `SessionReport.activity_log` существует | `grep -c "activity_log" v2/models/schemas.py >= 1` |

---

## 7. Pydantic модели (schemas.py)

| Модель | Назначение |
|--------|-----------|
| `RiskDefinition` | Риск из KB |
| `FactorDefinition` | UFR фактор |
| `MitigationDefinition` | UMF мера |
| `Mapping` | Связь risk → factor → mitigation |
| `KnowledgeBaseData` | Полная KB |
| `RiskConfig` | Выбранный риск + факторы + меры |
| `TestSession` | Конфигурация сессии |
| `Attack` | Атака (+ ground_truth, source_document для HALL) |
| `AttackResult` | Результат атаки |
| `MultiTurnChain` | Multi-turn цепочка |
| `MultiTurnResult` | Результат цепочки |
| `AttackDecision` | Решение планировщика |
| `EvolutionCycle` | Цикл эволюции (+ planner/review поля) |
| `RiskResult` | Итог по риску |
| `SessionReport` | Полный отчёт (+ all_attack_results, activity_log) |
