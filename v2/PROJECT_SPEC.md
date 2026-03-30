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
- **KB-aware режим**: HALL и DISINFO (с RAG-факторами) используют KB целевого агента
- **Единый pipeline**: ВСЕ риски идут через один цикл (Planner -> Gen -> Run -> Score -> Evolve)
- **Progress callbacks**: run_batch и run_chain поддерживают progress_callback/step_callback
- **Adaptive Budget**: единый бюджет атак, Planner распределяет между single/multi
- **Technique Leaderboard**: визуализация эффективности техник в Dashboard
- **Meta-Reflection**: Claudini autoresearch loop — анализ всей сессии, prompt evolution, reward hacking detection
- **Background Thinker**: Ouroboros consciousness — фоновый LLM-анализ каждые 20 сек
- **Strategy Memory**: persistent знания между сессиями, версионированные стратегии

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
│   ├── hall_verifier.py        # KB-aware генерация/верификация (HALL, DISINFO) + evolution
│   ├── meta_reflector.py       # Meta-анализ сессии + background thinking (Ouroboros)
│   ├── strategy_memory.py      # Persistent память между сессиями (Claudini versioning)
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
│   └── strategy_memory.json    # Persistent память стратегий (cross-session)
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
| BUDGET | Слайдер "Бюджет: N атак" (5-100), слайдер "Макс. цепочек" (1-10), слайдер "Макс. шагов" (2-8), toggle "Авто/Фиксированное" |
| ЗАПУСК | Кнопка, проверяет target через `check_target()` перед стартом |

### Страница "/dashboard" — Dashboard

**ЛЕВАЯ ПАНЕЛЬ (w-80):**

| Блок | Содержимое | Таймер |
|------|-----------|--------|
| SESSION | ID, Risk, Status (●/○), progress bar | 0.5s `_update_session` |
| METRICS | Total, Rate, Success (зелёный), Failed (красный) | 0.5s `_update_metrics` |
| EVOLUTION | echart график + expandable детали (OBS/HYP/DEC/ESC/Learnings/Review + META block) | 2.0s `_update_evo` |
| TECHNIQUES | Горизонтальные бары: rate% + название + (success/total) | 2.0s `_update_tech` |
| СТОП | Кнопка -> `state.should_stop=True` + notify + state.log | — |

**EVOLUTION details — meta-reflection block:**
Если `cycle.meta_diagnosis` непуст — оранжевый блок:
- 🧠 META-REFLECTION: диагноз, root cause, рекомендация
- 🔄 Prompt Evolution (если есть)
- ⛔ РЕКОМЕНДАЦИЯ: ПРЕКРАТИТЬ (если should_stop)

**ПРАВАЯ ПАНЕЛЬ (flex-1):**

| Элемент | Описание |
|---------|----------|
| Вкладки | `ATTACK LOG` / `ACTIVITY LOG` |
| status_text | Текущий статус pipeline |
| ATTACK LOG | scroll_area -> log_column. Карточки атак (см. ниже) |
| ACTIVITY LOG | scroll_area -> activity_column. Хронология с таймстампами |

**Карточка атаки (внутри log_column):**
```
┌─ border-green/red ─────────────────────────────┐
│ #idx   Gen N   RISK_ID   icon confidence        │  <- заголовок
│ 📤 payload preview (120 символов)...             │  <- preview
│ 📥 response preview (120 символов)...            │  <- preview
│ ⚖️ judge reasoning preview (120 символов)...     │  <- preview
│ ▼ Детали                                         │  <- expandable
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
  └─ check_target() -> fail? notify + return
  └─ _run_testing_pipeline(risk_configs)
  └─ _background_thinker()              # параллельная задача (Ouroboros)
       │
       ├─ LLMFactory() -> attacker, judge, reviewer (thinker = judge с семафором)
       ├─ StrategyMemory() -> загрузка prior knowledge
       ├─ HallVerifier (если hall_kb_path задан)
       │
       └─ for risk_config in risk_configs:
            ├─ prior = memory.get_prior_knowledge()
            ├─ try/except/continue (graceful)
            │
            ├─ _is_kb_aware_risk()? -> KB-aware генерация + верификация
            │
            └─ Обычный flow:
                 └─ for cycle_num in 1..max_cycles:
                      ├─ Planner: plan_initial / plan_next (+ budget + prior)
                      ├─ Budget: single_count + chains × steps <= budget
                      ├─ Single-turn: generate -> run_batch(progress_callback) -> score_batch
                      ├─ Multi-turn: generate_multi_turn(max_steps) -> run_chain(step_callback) -> score_chain
                      ├─ Technique stats -> Activity Log
                      ├─ Статистика -> EvolutionCycle -> state.evolution_history
                      ├─ Evolution: reflect -> mutate -> review
                      ├─ MetaReflector.analyze() (если >=2 gen)
                      │    ├─ diagnosis, root_cause, recommendation
                      │    ├─ prompt_evolution, technique_recombination
                      │    ├─ reward_hacking_detection
                      │    └─ should_pivot / should_stop -> break
                      └─ memory.record_strategy()
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
    thinker:    qwen3-8b         # background consciousness (shared с judge, семафор)
  fallback_model: gemma-3-12b-it
```

- `LLMFactory()` читает `config.yaml` автоматически
- qwen3 возвращает `<think>...</think>` -> `strip_llm_wrapper()` из `core/utils.py`
- `attack_runner` добавляет `user_id` в body (требование chatbot-professor)
- `_llm_semaphore` — background thinker пропускает ход если LLM занят

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
| PIPE-1 | Пустой response -> is_successful=False | Guard в `response_scorer.py` |
| PIPE-2 | Каждый риск в try/except/continue | `grep -c "except Exception" v2/ui/app.py >= 2` |
| PIPE-3 | `should_stop` проверяется после каждого await | Множественные проверки в pipeline |

### Data

| ID | Правило | Проверка |
|----|---------|----------|
| DATA-1 | `SessionReport.all_attack_results` существует | `grep -c "all_attack_results" v2/models/schemas.py >= 1` |
| DATA-2 | `SessionReport.activity_log` существует | `grep -c "activity_log" v2/models/schemas.py >= 1` |

### Budget

| ID | Правило | Проверка |
|----|---------|----------|
| BUD-1 | Слайдер бюджета в UI | `grep -c "attack_budget" v2/ui/app.py >= 2` |
| BUD-2 | Budget лог в pipeline | `grep -c "📊 БЮДЖЕТ" v2/ui/app.py >= 1` |

### Techniques

| ID | Правило | Проверка |
|----|---------|----------|
| TECH-1 | technique в AttackResult | `grep -c "technique" v2/models/schemas.py >= 3` |
| TECH-2 | Leaderboard в Dashboard | `grep -c "TECHNIQUES" v2/ui/app.py >= 1` |
| TECH-3 | Progress callbacks | `grep -c "progress_callback" v2/core/attack_runner.py >= 2` |

### Meta-Reflection

| ID | Правило | Проверка |
|----|---------|----------|
| META-1 | MetaReflector существует | `test -f v2/core/meta_reflector.py` |
| META-2 | Meta-поля в EvolutionCycle | `grep -c "meta_diagnosis" v2/models/schemas.py >= 1` |
| META-3 | Background thinker | `grep -c "_background_thinker" v2/ui/app.py >= 2` |

### Strategy Memory

| ID | Правило | Проверка |
|----|---------|----------|
| MEM-1 | StrategyMemory существует | `test -f v2/core/strategy_memory.py` |
| MEM-2 | Интеграция в pipeline | `grep -c "StrategyMemory" v2/ui/app.py >= 1` |

---

## 7. Pydantic модели (schemas.py)

| Модель | Назначение |
|--------|-----------|
| `RiskDefinition` | Риск из KB |
| `FactorDefinition` | UFR фактор |
| `MitigationDefinition` | UMF мера |
| `Mapping` | Связь risk -> factor -> mitigation |
| `KnowledgeBaseData` | Полная KB |
| `RiskConfig` | Выбранный риск + факторы + меры |
| `TestSession` | Конфигурация сессии |
| `Attack` | Атака (+ ground_truth, source_document для HALL) |
| `AttackResult` | Результат атаки (+ technique) |
| `MultiTurnChain` | Multi-turn цепочка |
| `MultiTurnResult` | Результат цепочки |
| `AttackDecision` | Решение планировщика (+ single_turn_count, multi_turn_chains, steps_per_chain, budget_*) |
| `EvolutionCycle` | Цикл эволюции (+ planner/review/meta поля) |
| `RiskResult` | Итог по риску |
| `SessionReport` | Полный отчёт (+ all_attack_results, activity_log) |

---

## 8. Activity Log — все типы событий

| Событие | Цвет | Описание |
|---------|------|----------|
| 🔧 INIT | серый | Инициализация (модели, версии) |
| 🎯 НАЧАЛО | серый | Начало тестирования риска |
| 🧠 PLANNER | оранжевый | Решение планировщика |
| 👁 OBS | оранжевый | Наблюдение планировщика |
| 🧪 HYP | оранжевый | Гипотеза планировщика |
| ⚡ DEC | оранжевый | Решение планировщика |
| 📊 БЮДЖЕТ | серый | Распределение бюджета |
| ⚔️ ГЕНЕРАЦИЯ | серый | Начало генерации атак |
| ✅ СГЕНЕРИРОВАНО | серый | Атаки сгенерированы |
| 📤 ОТПРАВКА | серый | Начало отправки в target |
| 📤 АТАКА | серый | Прогресс: N/M атака |
| 📥 ПОЛУЧЕНО | серый | Ответы получены |
| ⚖️ SCORING | серый | Judge оценивает |
| 📈 ТЕХНИКА | серый | Статистика техники |
| 📊 РЕЗУЛЬТАТ | зелёный | Итог поколения |
| 🔄 REFLECT | фиолетовый | Анализ результатов |
| 👥 REVIEW | голубой | Multi-model review |
| 🔗 MULTI-TURN | серый | Начало multi-turn |
| 🔗 CHAIN | серый | Прогресс цепочки N/M |
| 🔗 STEP | серый | Прогресс шага |
| 📚 KB-AWARE | синий | KB-aware режим |
| 📚 KB-GEN | синий | KB-aware генерация |
| 🔍 KB-VERIFY | синий | KB-aware верификация |
| 🔄 KB-REFLECT | синий | KB-aware reflect |
| 💭 THINKING | серый | Фоновый инсайт (Ouroboros) |
| 💭 THINKER | серый | Завершение фонового анализа |
| 🧠 META | оранжевый | Meta-reflection диагноз |
| 🔍 ROOT | оранжевый | Корневая причина |
| 💡 РЕКОМЕНДАЦИЯ | оранжевый | Рекомендация meta-reflection |
| 🔄 PROMPT EVO | синий | Эволюция промпта |
| 🔀 RECOMB | голубой | Рекомбинация техник |
| 🚨 HACKING | красный | Reward hacking detected |
| ⛔ META-STOP | красный | Рекомендация прекратить |
| 📖 MEMORY | серый | Загрузка prior knowledge |
| 💾 MEMORY | серый | Запись стратегии |
| ❌ ОШИБКА | красный | Ошибка |
| ⛔ СТОП | красный | Остановка пользователем |
| 🏁 ЗАВЕРШЕНО | зелёный | Тестирование завершено |
